import { useState, useEffect } from 'react';
import { db } from '../lib/firebase';
import { doc, onSnapshot, collection, query, orderBy, limit } from 'firebase/firestore';

export default function Dashboard() {
  const [todayCount, setTodayCount] = useState(0);
  const [status, setStatus] = useState('OFFLINE');
  const [lastUpdate, setLastUpdate] = useState(null);
  const [lastTravelTime, setLastTravelTime] = useState(null);
  const [recentCounts, setRecentCounts] = useState([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    // Listen to live counter document
    const liveUnsub = onSnapshot(
      doc(db, 'live', 'furnace'),
      (doc) => {
        if (doc.exists()) {
          const data = doc.data();
          setTodayCount(data.today_count || 0);
          setStatus(data.status || 'OFFLINE');
          setLastTravelTime(data.last_travel_time || null);
          if (data.last_count) {
            setLastUpdate(data.last_count.toDate());
          } else {
             setLastUpdate(null);
          }
          setConnected(true);
        }
      },
      (error) => {
        console.error('Live listener error:', error);
        setConnected(false);
      }
    );

    // Listen to recent counts
    const countsQuery = query(
      collection(db, 'counts'),
      orderBy('timestamp', 'desc'),
      limit(5)
    );
    
    const countsUnsub = onSnapshot(countsQuery, (snapshot) => {
      const counts = snapshot.docs.map(doc => {
        const data = doc.data();
        // Use consistent formatting with utils.js but inline for simplicity here
        const timeStr = data.timestamp?.toDate()?.toLocaleTimeString('en-IN', {
          hour: '2-digit', 
          minute: '2-digit', 
          second: '2-digit',
          hour12: true
        }) || '--:--:--';
        
        return {
          time: timeStr,
          travel: data.travel_time ? `${data.travel_time.toFixed(1)}s` : '--'
        };
      });
      setRecentCounts(counts);
    });

    return () => {
      liveUnsub();
      countsUnsub();
    };
  }, []);

  const getStatusColor = () => {
    switch (status) {
      case 'RUNNING': return 'bg-green-500';
      case 'BREAK': return 'bg-yellow-500';
      default: return 'bg-red-500';
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'RUNNING': return 'Mill Running';
      case 'BREAK': return 'Break';
      default: return 'Offline';
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-4 py-3">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold">AIS Production</h1>
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${getStatusColor()} ${status === 'RUNNING' ? 'animate-pulse' : ''}`}></div>
            <span className="text-sm text-gray-300">{getStatusText()}</span>
          </div>
        </div>
        <p className="text-sm text-gray-400 mt-1">Furnace Camera - Plate Scrap Counter</p>
      </header>

      {/* Main Count Display */}
      <main className="p-4">
        {/* Big Count Card */}
        <div className="bg-gradient-to-br from-blue-600 to-blue-800 rounded-2xl p-6 mb-4 shadow-lg">
          <div className="text-center">
            <p className="text-blue-200 text-sm uppercase tracking-wider mb-2">Pieces Today</p>
            <p className="text-7xl font-bold tabular-nums">{todayCount}</p>
            <p className="text-blue-200 text-sm mt-2">
              Last count: {lastUpdate ? lastUpdate.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }) : '--:--:--'}
            </p>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div className="bg-gray-800 rounded-xl p-4">
            <p className="text-gray-400 text-xs uppercase">Last Travel</p>
            <p className="text-2xl font-bold">
              {lastTravelTime ? `${lastTravelTime.toFixed(1)}s` : '--'}
            </p>
          </div>
          <div className="bg-gray-800 rounded-xl p-4">
            <p className="text-gray-400 text-xs uppercase">Status</p>
            <p className="text-2xl font-bold">{status}</p>
          </div>
        </div>

        {/* Recent Counts */}
        <div className="bg-gray-800 rounded-xl p-4">
          <h2 className="text-gray-400 text-xs uppercase mb-3">Recent Counts</h2>
          {recentCounts.length > 0 ? (
            <div className="space-y-2">
              {recentCounts.map((item, index) => (
                <div key={index} className="flex justify-between items-center py-2 border-b border-gray-700 last:border-0">
                  <span className="text-gray-300">{item.time}</span>
                  <span className="text-gray-500 text-sm">Travel: {item.travel}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-center py-4">No counts yet today</p>
          )}
        </div>

        {/* Connection Status */}
        {!connected && (
          <div className="mt-4 bg-red-900/50 border border-red-600 rounded-lg p-3 text-center">
            <p className="text-red-200 text-sm">
              Connecting to Firebase...
            </p>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="fixed bottom-0 left-0 right-0 bg-gray-800 border-t border-gray-700 px-4 py-2">
        <div className="flex justify-between text-xs text-gray-500">
          <span>CAM-1 Furnace</span>
          <span>{connected ? '🟢 Live' : '🔴 Offline'}</span>
        </div>
      </footer>
    </div>
  );
}
