"""
Resource Monitor - Production Grade
Based on professional video editing apps (CapCut, Premiere Pro, DaVinci Resolve)

Prevents system freezes by:
- Limiting CPU cores (leave headroom for OS)
- Monitoring RAM usage
- Setting appropriate process priority
- Graceful degradation under load
"""

import os
import sys
import time
import psutil
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class ResourceLimits:
    """Production-grade resource limits with dynamic adjustment"""
    
    # CPU Limits (Dynamic by machine class)
    max_cpu_percent: float = 85.0  # Will be adjusted by machine class
    max_threads_ratio: float = 0.75  # Will be adjusted by machine class
    min_threads: int = 2  # Always use at least 2 threads
    max_threads: int = 16  # Cap at 16 threads (diminishing returns)
    
    # Memory Limits (Professional app standard)
    min_free_ram_percent: float = 5.0  # Pause if < 10% RAM free
    resume_ram_percent: float = 8.0  # Resume when > 15% RAM free
    max_ram_usage_percent: float = 90.0  # Don't exceed 90% total RAM
    memory_check_interval: int = 3  # Check every 3 seconds
    
    # Process Priority (Background processing)
    nice_value: int = 5  # Slightly lower priority (balanced)

class MachineClass:
    """Detect machine class for dynamic resource adjustment"""
    
    @staticmethod
    def detect() -> str:
        """
        Detect if machine is low-end laptop or high-end desktop
        
        Returns:
            'low_end' or 'high_end'
        """
        cores = os.cpu_count() or 4
        ram_gb = psutil.virtual_memory().total / (1024**3)
        
        # Low-end detection:
        # - <= 4 cores
        # - <= 8GB RAM
        # - OR laptop with <= 6 cores
        if cores <= 4 or ram_gb <= 8:
            return 'low_end'
        
        # Check if laptop (battery present)
        try:
            battery = psutil.sensors_battery()
            if battery is not None and cores <= 6:
                return 'low_end'  # Laptop with <= 6 cores
        except:
            pass
        
        # High-end: 8+ cores, 16+ GB RAM, or desktop
        if cores >= 8 and ram_gb >= 16:
            return 'high_end'
        
        # Default to low_end for safety
        return 'low_end'
    
    @staticmethod
    def get_cpu_limit(machine_class: str) -> float:
        """
        Get CPU limit based on machine class
        
        Args:
            machine_class: 'low_end' or 'high_end'
            
        Returns:
            float: Max CPU usage percent
        """
        if machine_class == 'low_end':
            return 75.0  # 70-75% for laptops
        else:
            return 90.0  # 90% for high-end desktops
    
    @staticmethod
    def get_threads_ratio(machine_class: str) -> float:
        """
        Get threads ratio based on machine class
        
        Args:
            machine_class: 'low_end' or 'high_end'
            
        Returns:
            float: Thread allocation ratio
        """
        if machine_class == 'low_end':
            return 0.70  # 70% for laptops
        else:
            return 0.85  # 85% for high-end desktops


class ResourceMonitor:
    """
    Production-grade resource monitor with dynamic adjustment
    Ensures app doesn't freeze user's system
    """
    
    def __init__(self, limits: Optional[ResourceLimits] = None):
        self.limits = limits or ResourceLimits()
        self._lock = threading.Lock()
        self._last_memory_check = 0
        self._process = psutil.Process()
        
        # Detect system capabilities
        self.total_cores = os.cpu_count() or 4
        self.total_ram_gb = psutil.virtual_memory().total / (1024**3)
        
        # Detect machine class (low-end laptop vs high-end desktop)
        self.machine_class = MachineClass.detect()
        
        # Apply dynamic limits based on machine class
        self.limits.max_cpu_percent = MachineClass.get_cpu_limit(self.machine_class)
        self.limits.max_threads_ratio = MachineClass.get_threads_ratio(self.machine_class)
        
        # Set priority based on machine class
        # High end -> Normal priority
        # Low end -> Background priority
        if self.machine_class == 'high_end':
            self.limits.nice_value = 0 # Normal
        else:
            self.limits.nice_value = 5 # Background
            
        # Calculate optimal threads
        self._optimal_threads = self._calculate_optimal_threads()
        
        self.set_process_priority()
        
        print(f"[ResourceMonitor] Machine: {self.machine_class.upper()}")
        print(f"[ResourceMonitor] System: {self.total_cores} cores, {self.total_ram_gb:.1f}GB RAM")
        print(f"[ResourceMonitor] Limits: {self.limits.max_cpu_percent:.0f}% CPU, {self._optimal_threads} threads")
        print(f"[ResourceMonitor] Priority: {'Normal' if self.limits.nice_value == 0 else 'Background'}")
    
    def _calculate_optimal_threads(self) -> int:
        """
        Calculate optimal thread count based on CPU cores
        Formula: min(cores - 1, 16) for best balance
        """
        # Dynamic based on machine class
        if self.machine_class == 'high_end':
             # Turbo-like: Use cores - 1 (leave 1 for system)
             threads = max(self.limits.min_threads, self.total_cores - 1)
        else:
             # Eco-like:
             if self.total_cores >= 8:
                 # On 8-core macs (M1/M2/M3), taking 7 cores makes UI laggy. Leave 2 free.
                 threads = max(self.limits.min_threads, self.total_cores - 2)
             else:
                 # For 4-6 core machines, leaving 2 free might be too slow (50% perf loss on 4 cores)
                 # So we stick to N-1 for these.
                 threads = max(self.limits.min_threads, self.total_cores - 1)
        
        # Cap at max threads (diminishing returns beyond 16)
        threads = min(threads, self.limits.max_threads)
        
        return threads
    
    def get_max_threads(self) -> int:
        """
        Get maximum threads for FFmpeg/Whisper
        
        Returns:
            int: Number of threads to use
        """
        return self._optimal_threads
    
    def can_process(self) -> bool:
        """
        Check if system has enough resources to process
        
        Returns:
            bool: True if resources available, False otherwise
        """
        # Check memory (most critical)
        if not self._check_memory():
            return False
        
        # Check CPU (less critical, just informational)
        cpu_percent = psutil.cpu_percent(interval=0.1)
        if cpu_percent > 95:
            # print(f"[ResourceMonitor] High CPU usage: {cpu_percent}%")
            # Don't block, just warn
            pass
        
        return True
    
    def _check_memory(self) -> bool:
        """
        Check if enough memory available
        Uses production-grade thresholds with auto-resume
        """
        current_time = time.time()
        
        # Rate limit memory checks (expensive operation)
        if current_time - self._last_memory_check < self.limits.memory_check_interval:
            return True
        
        self._last_memory_check = current_time
        
        mem = psutil.virtual_memory()
        available_percent = (mem.available / mem.total) * 100
        
        # Pause if below minimum threshold
        if available_percent < self.limits.min_free_ram_percent:
            print(f"[ResourceMonitor] Low memory: {available_percent:.1f}% free (need {self.limits.min_free_ram_percent}%)")
            return False
        
        # Auto-resume when above resume threshold (25%)
        if available_percent >= self.limits.resume_ram_percent:
            return True
        
        return True
    
    def wait_for_resources(self, timeout: int = 60, check_interval: int = 5) -> bool:
        """
        Wait until resources become available
        Auto-resumes when RAM > 25%
        
        Args:
            timeout: Max seconds to wait
            check_interval: Seconds between checks
            
        Returns:
            bool: True if resources available, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            mem = psutil.virtual_memory()
            available_percent = (mem.available / mem.total) * 100
            
            # Auto-resume when RAM > 25%
            if available_percent >= self.limits.resume_ram_percent:
                print(f"[ResourceMonitor] Resources available! RAM: {available_percent:.1f}% free")
                return True
            
            elapsed = int(time.time() - start_time)
            print(f"[ResourceMonitor] Waiting for RAM > {self.limits.resume_ram_percent}% (currently {available_percent:.1f}%) - {elapsed}s elapsed")
            time.sleep(check_interval)
        
        print(f"[ResourceMonitor] Timeout waiting for resources")
        return False
    
    def set_process_priority(self):
        """
        Set process priority to background/low
        Ensures UI and other apps remain responsive
        """
        try:
            if sys.platform == 'darwin':  # macOS
                # nice value: 0=normal, 20=lowest
                self._process.nice(self.limits.nice_value)
                print(f"[ResourceMonitor] Set process priority: nice={self.limits.nice_value}")
                
            elif sys.platform == 'win32':  # Windows
                import psutil
                if self.limits.nice_value == 0:
                     self._process.nice(psutil.NORMAL_PRIORITY_CLASS)
                     print(f"[ResourceMonitor] Set process priority: NORMAL")
                else:
                     self._process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                     print(f"[ResourceMonitor] Set process priority: BELOW_NORMAL")
                
            else:  # Linux
                self._process.nice(self.limits.nice_value)
                print(f"[ResourceMonitor] Set process priority: nice={self.limits.nice_value}")
                
        except Exception as e:
            print(f"[ResourceMonitor] Failed to set priority: {e}")
    
    def get_ffmpeg_threads(self) -> int:
        """
        Get optimal thread count for FFmpeg
        Formula: min(cores - 1, 16)
        """
        # FFmpeg optimal
        if self.machine_class == 'high_end':
            threads = min(self.total_cores - 1, 16)
        else:  # low end
            # UPDATED: Use -1 instead of -2
            threads = min(self.total_cores - 1, 16)
        
        # Ensure minimum threads
        threads = max(self.limits.min_threads, threads)
        
        return threads
    
    def get_whisper_threads(self) -> int:
        """
        Get optimal thread count for Whisper
        Whisper benefits from more threads
        """
        return self._optimal_threads
    
    def get_optimal_worker_config(self) -> tuple[int, int]:
        """
        Get optimal (max_workers, threads_per_worker) for video processing
        
        Returns:
            tuple: (max_workers, threads_per_worker)
        """
        
        if self.machine_class == 'low_end':
            # 1 worker is safest for stability
            max_workers = 1
            # Threads: Use optimal threads (limited by cores-2)
            threads_per_worker = self.get_ffmpeg_threads()
            
        else: # High End
            # Aggressive
            if self.total_ram_gb >= 16:
                # If we have lots of cores and RAM, 2 workers might be faster
                # But parallel renders essentially double RAM usage.
                max_workers = 2 
                # Split threads between workers
                threads_per_worker = max(2, self.total_cores // 2)
            else:
                # High end cpu but low ram: still 1 worker, but max threads
                max_workers = 1
                threads_per_worker = max(2, self.total_cores - 1)
                
        return max_workers, threads_per_worker
    
    def get_system_info(self) -> Dict[str, Any]:
        """
        Get current system resource usage
        Useful for monitoring/debugging
        """
        mem = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        return {
            'cpu': {
                'total_cores': self.total_cores,
                'usage_percent': cpu_percent,
                'threads_allocated': self._optimal_threads,
            },
            'memory': {
                'total_gb': self.total_ram_gb,
                'available_gb': mem.available / (1024**3),
                'available_percent': (mem.available / mem.total) * 100,
                'used_percent': mem.percent,
            },
            'limits': {
                'max_threads': self._optimal_threads,
                'min_free_ram_percent': self.limits.min_free_ram_percent,
                'resume_ram_percent': self.limits.resume_ram_percent,
            },
            'machine_class': self.machine_class,
        }


# Global instance (singleton pattern)
_resource_monitor: Optional[ResourceMonitor] = None

def get_resource_monitor() -> ResourceMonitor:
    """Get global ResourceMonitor instance"""
    global _resource_monitor
    if _resource_monitor is None:
        _resource_monitor = ResourceMonitor()
    return _resource_monitor


# Convenience functions
def can_process() -> bool:
    """Check if resources available for processing"""
    return get_resource_monitor().can_process()

def get_max_threads() -> int:
    """Get max threads for processing"""
    return get_resource_monitor().get_max_threads()

def wait_for_resources(timeout: int = 60) -> bool:
    """Wait for resources to become available"""
    return get_resource_monitor().wait_for_resources(timeout)

def set_process_priority():
    """Set process to background priority"""
    get_resource_monitor().set_process_priority()
