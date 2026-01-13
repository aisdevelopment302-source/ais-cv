// Firebase configuration and initialization
import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js';
import { getFirestore } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js';

const firebaseConfig = {
  apiKey: "AIzaSyCBXxSsvjnFzGMMFbHCYouokIQydObeElo",
  authDomain: "ais-production-e013c.firebaseapp.com",
  projectId: "ais-production-e013c",
  storageBucket: "ais-production-e013c.firebasestorage.app",
  messagingSenderId: "565647781984",
  appId: "1:565647781984:web:0f05c2436afdcc7a0b1305"
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
