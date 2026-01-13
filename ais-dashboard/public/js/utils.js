// Utility functions for AIS Dashboard

// Format date for display
export function formatDate(dateStr) {
  const date = new Date(dateStr + 'T00:00:00');
  return date.toLocaleDateString('en-IN', { 
    weekday: 'long', 
    year: 'numeric', 
    month: 'long', 
    day: 'numeric' 
  });
}

// Format short date
export function formatShortDate(dateStr) {
  const date = new Date(dateStr + 'T00:00:00');
  return date.toLocaleDateString('en-IN', { 
    month: 'short', 
    day: 'numeric' 
  });
}

// Format time from timestamp
export function formatTime(timestamp) {
  if (!timestamp) return '--:--';
  const date = timestamp.toDate ? timestamp.toDate() : new Date(timestamp);
  return date.toLocaleTimeString('en-IN', { 
    hour: '2-digit', 
    minute: '2-digit',
    hour12: true 
  });
}

// Format minutes to hours and minutes - handles fractional minutes properly
export function formatDuration(minutes) {
  if (minutes === null || minutes === undefined || minutes === 0) return '0m';
  // Round up any fractional minutes so they're visible
  const totalMins = Math.ceil(minutes);
  if (totalMins < 1) return '<1m';
  const hrs = Math.floor(totalMins / 60);
  const mins = totalMins % 60;
  if (hrs > 0) {
    return `${hrs}h ${mins}m`;
  }
  return `${mins}m`;
}

// Get today's date as YYYY-MM-DD
export function getTodayDate() {
  return new Date().toISOString().split('T')[0];
}

// Get date N days ago as YYYY-MM-DD
export function getDateDaysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().split('T')[0];
}

// Status color helpers
export function getStatusColor(status) {
  switch (status) {
    case 'RUNNING': return 'bg-green-500';
    case 'BREAK': return 'bg-yellow-500';
    default: return 'bg-red-500';
  }
}

export function getStatusText(status) {
  switch (status) {
    case 'RUNNING': return 'Mill Running';
    case 'BREAK': return 'Break';
    default: return 'Offline';
  }
}

// Generate hour labels (00 to 23)
export function getHourLabels() {
  return Array.from({ length: 24 }, (_, i) => i.toString().padStart(2, '0'));
}

// Calculate percentage for progress bar
export function calcPercent(value, max) {
  if (!max || max === 0) return 0;
  return Math.min(100, Math.round((value / max) * 100));
}
