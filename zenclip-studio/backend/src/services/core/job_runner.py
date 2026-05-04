from utils.logger import log
import utils.encoding_fix
import os
import time
import json

from services.core.job_manager import job_manager, JobStatus
from services.core.resource_monitor import get_resource_monitor, set_process_priority
from services.media.audio_transcriber import clean_repetitive_content, clean_phrase_level_repetition


# We need to import the actual logic functions.
# Since I haven't refactored tasks.py yet, I will import them as is and adapt.
# But `tasks.py` currently relies on global `jobs` dict.
# I MUST refactor `tasks.py` BEFORE `job_runner.py` works perfectly.
# strategies:
# 1. Create job_runner.py with placeholders calling stateless versions of tasks.
# 2. Refactor tasks.py to be stateless.

# Let's create job_runner first with the INTENTION of calling stateless functions.

class JobRunner:
    def __init__(self, job_id, jobs_dir):
        self.job_id = job_id
        self.jobs_dir = jobs_dir
        self.job_dir = os.path.join(jobs_dir, job_id)
        
        # Initialize resource monitor
        self.resource_monitor = get_resource_monitor()
        
        # Set process priority to background (production-grade)
        set_process_priority()
        
    def _load_metadata(self):
        with open(os.path.join(self.job_dir, "metadata.json"), 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_artifact(self, filename, data):
        with open(os.path.join(self.job_dir, filename), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_artifact(self, filename):
        path = os.path.join(self.job_dir, filename)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def _is_cancelled(self):
        """Checks if the job has been marked as cancelled."""
        meta = self._load_metadata()
        if meta and meta.get('status') == JobStatus.CANCELLED.value:
            log.warn(f"Cancellation detected, stopping runner", module="JobRunner", job=self.job_id)
            return True
        return False

    def _parse_time_str(self, time_str):
        try:
            if not time_str: return 0.0
            parts = str(time_str).split(':')
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            return float(time_str)
        except:
            return 0.0

    def run(self):
        """
        Main execution pipeline.
        Checks for existing artifacts to determine if steps can be skipped (Resume).
        """
        if self._is_cancelled(): return

        meta = self._load_metadata()
        data = meta['data']
        
        # 1. PREPARING (Download or Upload Verification)
        job_manager.update_job_status(self.job_id, JobStatus.PREPARING, "Preparing video...", progress_percent=10)
        
        video_path = None
        video_info_path = os.path.join(self.job_dir, "video_info.json")
        
        if os.path.exists(video_info_path):
            video_info = self._load_artifact("video_info.json")
            video_path = video_info['path']
            log.info(f"Resuming: video already downloaded", module="JobRunner")
        else:
            # Execute Download/Prep
            try:
                if 'video_file' in data: # Upload case (logic might vary if we just passed path)
                     # In existing app.py, upload is saved immediately.
                     # data should contain 'filepath'
                     video_path = data.get('filepath') 
                     # Verify existence
                     if not os.path.exists(video_path):
                         raise FileNotFoundError(f"Uploaded file missing: {video_path}")
                
                elif 'url' in data: # YouTube case (Deprecated)
                     # Logic Removed
                     raise ValueError("URL download is no longer supported. Please upload a file.")
                
                self._save_artifact("video_info.json", {"path": video_path})
            
            except Exception as e:
                # Retry handled by loop? Or just fail?
                # For now fail.
                raise e

        if self._is_cancelled(): return

        # 2. TRANSCRIBING
        job_manager.update_job_status(self.job_id, JobStatus.TRANSCRIBING, "Extracting transcript (AI)...", progress_percent=30)
        
        transcript_path = os.path.join(self.job_dir, "transcript.json")
        phrase_timings = None
        language = 'en'
        
        if os.path.exists(transcript_path):
             phrase_timings = self._load_artifact("transcript.json")
             # CRITICAL FIX: Clean Repetition on resume/manual steps
             
             phrase_timings = clean_repetitive_content(phrase_timings)
             phrase_timings = clean_phrase_level_repetition(phrase_timings)
             
             language = meta.get('data', {}).get('language', 'en')
             log.info(f"Resuming: transcript found ({len(phrase_timings)} phrases, lang={language})", module="JobRunner")
        else:
            from services.core.tasks_stateless import transcribe_step
            # params: video_path, mode
            mode = data.get('transcription_mode', 'fast')
            # CHECK_CANCELLED: Pass callback to allow deep cancellation during transcription
            phrase_timings, language = transcribe_step(video_path, mode, check_cancelled=self._is_cancelled)
            self._save_artifact("transcript.json", phrase_timings)
            
            # Save detected language to metadata for future use
            job_manager.update_job_data(self.job_id, {'language': language})
            # Also update local 'data' dict so analyze step uses it if we re-read? 
            # Actually we pass 'language' variable directly.

        if self._is_cancelled(): return

        # 3. ANALYZING
        job_manager.update_job_status(self.job_id, JobStatus.ANALYZING, "Analyzing content for viral clips...", progress_percent=60)
        
        analysis_path = os.path.join(self.job_dir, "analysis.json")
        clips_data = None
        
        if os.path.exists(analysis_path):
            clips_data = self._load_artifact("analysis.json")
            log.info(f"Resuming: analysis found ({len(clips_data)} clips)", module="JobRunner")
        elif data.get('manual_cut', False):
            # MANUAL CUT MODE
            log.info("Manual cut mode", module="JobRunner")
            # Disable auto-extension for manual cuts
            data['min_duration'] = 0
            import json
            
            manual_segments = []
            try:
                ms_raw = data.get('manual_segments', '[]')
                if ms_raw and ms_raw != 'None':
                     manual_segments = json.loads(ms_raw)
            except Exception as e:
                log.warn(f"Failed to parse manual_segments: {e}", module="JobRunner")

            clips_data = []

            # If we have segments, use them
            if manual_segments and isinstance(manual_segments, list) and len(manual_segments) > 0:
                # Enforce Max 5 Limit for Manual
                if len(manual_segments) > 5:
                    log.warn(f"Too many segments, limiting to 5", module="JobRunner")
                    manual_segments = manual_segments[:5]
                
                log.info(f"Processing {len(manual_segments)} manual segments", module="JobRunner")
                for i, seg in enumerate(manual_segments):
                    # Frontend usually sends {id, start, end}
                    start_str = seg.get('start', '00:00')
                    end_str = seg.get('end', '00:30')
                    
                    start_time = self._parse_time_str(start_str)
                    end_time = self._parse_time_str(end_str)
                    
                    # Validation and warnings
                    if start_time == 0.0 and start_str not in ['0', '00:00', '0:00']:
                        log.warn(f"Segment {i+1}: bad start time '{start_str}', defaulting to 00:00", module="JobRunner")
                    
                    if end_time == 0.0 and end_str not in ['0', '00:00', '0:00']:
                        log.warn(f"Segment {i+1}: bad end time '{end_str}', defaulting to 00:00", module="JobRunner")
                    
                    # Check for invalid range
                    if end_time <= start_time:
                        log.warn(f"Segment {i+1}: invalid range {start_str}→{end_str}", module="JobRunner")
                        
                        end_time = start_time + 30
                    
                    # Check for very short clips
                    duration = end_time - start_time
                    if duration < 1.0:
                        print(f"[INFO] Segment {i+1}: Short clip detected ({duration:.2f}s)")
                    
                    clips_data.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "topic": "Manual Cut",
                        "viral_score": 100,
                        "reason": f"Manual Selection {i+1}",
                        "hook_heading": "Manual Clip",
                        "hook_subheading": "",
                        "viral_caption": "Manual Clip"
                    })
            else:
                # Legacy Fallback (single start/end)
                start_time = self._parse_time_str(data.get('manual_start', '0'))
                end_time = self._parse_time_str(data.get('manual_end', '0'))

                if end_time <= start_time:
                     print(f"[WARN] Invalid manual times {start_time}-{end_time}, forcing 30s")
                     end_time = start_time + 30
                     
                clips_data = [{
                    "start_time": start_time,
                    "end_time": end_time,
                    "topic": "Manual Cut",
                    "viral_score": 100,
                    "reason": "User manual selection",
                    "hook_heading": "Manual Clip",
                    "hook_subheading": "",
                    "viral_caption": "Manual Clip"
                }]
            
            self._save_artifact("analysis.json", clips_data)
        else:
            from services.core.tasks_stateless import analyze_step
            # params: transcript, num_clips, min_duration, ...
            # I need flexible params from data
            # Determine hook style for prompt optimization
            hook_style = 'preset-1'
            if data.get('add_viral_hook') and data.get('hook_styles'):
                hook_style = data['hook_styles'].get('hook_style', 'preset-1')

            # CHECK_CANCELLED: Pass callback to allow deep cancellation during analysis
            clips_data = analyze_step(
                phrase_timings, 
                min(data.get('num_clips', 3), 5),  # Enforce Max 5 Limit for Auto 
                data.get('min_duration', 30),
                data.get('video_type', 'general'),
                data.get('custom_prompt'),
                data.get('api_key'),
                data.get('api_provider'),
                hook_style=hook_style,
                language=language,
                check_cancelled=self._is_cancelled
            )
            self._save_artifact("analysis.json", clips_data)

        if self._is_cancelled(): return

        # 4. WAITING_REVIEW (Optional)
        # If the flow demands review, we stop here.
        # Check data['require_review'] or similar.
        # Existing logic: extract_transcript endpoint stops here. process endpoint continues.
        # Let's support an explicit flag.
        if data.get('stop_for_review', False):
            job_manager.update_job_status(self.job_id, JobStatus.WAITING_REVIEW, "Waiting for user review...", progress_percent=70)
            return # Exit runner. Resume will happen when user calls "continue"

        if self._is_cancelled(): return

        # 5. CUTTING
        job_manager.update_job_status(self.job_id, JobStatus.CUTTING, "Cutting and processing clips...", progress_percent=80)
        
        # We don't skip cutting usually because it might be partial or parameters changed?
        # Maybe skip if 'clips_result.json' exists?
        clips_result_path = os.path.join(self.job_dir, "clips_result.json")
        clips_info = []

        if os.path.exists(clips_result_path):
             clips_info = self._load_artifact("clips_result.json")
             print("[INFO] Resuming: Cutting already done")
        else:
            from services.core.tasks_stateless import cut_step
            
            # Define progress callback to map cutting progress (0.0-1.0) to job progress (80%-95%)
            def _on_cut_progress(progress_fraction):
                """Maps cutting progress to overall job progress from 80% to 95%"""
                if progress_fraction < 0.0 or progress_fraction > 1.0:
                    return
                # Map 0.0-1.0 to 80-95%
                job_progress = 80 + int(progress_fraction * 15)
                job_manager.update_job_status(
                    self.job_id, 
                    JobStatus.CUTTING, 
                    f"Processing clips... ({job_progress}%)", 
                    progress_percent=job_progress
                )
            
            clips_info = cut_step(
                video_path,
                clips_data,
                phrase_timings,
                data, # config for subtitles, hooks, etc
                self.job_id, # Pass job_id for unique folder
                progress_callback=_on_cut_progress,
                check_cancelled=self._is_cancelled
            )
            self._save_artifact("clips_result.json", clips_info)

        # 6. DONE
        from services.core.job_manager import JobManager
        # Re-import to avoid scope issues if needed, or use job_manager singleton
        
        # update metadata with results
        meta = self._load_metadata()
        meta['clips'] = clips_info
        self._save_artifact("metadata.json", meta)
        
        job_manager.update_job_status(self.job_id, JobStatus.COMPLETE, "Completed!", progress_percent=100)

