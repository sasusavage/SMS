/**
 * SmartSchool Service Worker
 * Offline-first shell caching + IndexedDB queue for Background Sync.
 *
 * Offline queues:
 *   - 'attendance-queue'  → POST /classes/<id>/attendance
 *   - 'scores-queue'      → POST /assessments/*/save-scores
 *
 * Usage from page JS:
 *   navigator.serviceWorker.controller.postMessage({
 *     type: 'ENQUEUE',
 *     store: 'attendance-queue',
 *     payload: { url: '/classes/3/attendance', body: formBodyString }
 *   });
 */

const SHELL_CACHE  = 'smartschool-shell-v2';
const SHELL_ASSETS = [
    '/',
    '/static/css/main.css',
    '/static/img/icon.png',
    '/static/manifest.json',
];

const DB_NAME    = 'smartschool-offline';
const DB_VERSION = 1;
const STORES     = ['attendance-queue', 'scores-queue'];

// ── Install: pre-cache shell ──────────────────────────────────────────────────
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(SHELL_CACHE)
            .then(cache => cache.addAll(SHELL_ASSETS))
            .then(() => self.skipWaiting())
    );
});

// ── Activate: remove old caches ───────────────────────────────────────────────
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => k !== SHELL_CACHE).map(k => caches.delete(k))
            )
        ).then(() => self.clients.claim())
    );
});

// ── Fetch: cache-first for static assets, network-first for pages ─────────────
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // Only intercept same-origin GETs
    if (request.method !== 'GET' || url.origin !== self.location.origin) return;

    if (url.pathname.startsWith('/static/')) {
        // Static assets → cache first
        event.respondWith(
            caches.match(request).then(cached => cached || fetch(request))
        );
    } else {
        // Pages → network first, fall back to cache
        event.respondWith(
            fetch(request)
                .then(response => {
                    const clone = response.clone();
                    caches.open(SHELL_CACHE).then(c => c.put(request, clone));
                    return response;
                })
                .catch(() => caches.match(request))
        );
    }
});

// ── IndexedDB helpers ─────────────────────────────────────────────────────────
function openDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = e => {
            const db = e.target.result;
            STORES.forEach(name => {
                if (!db.objectStoreNames.contains(name)) {
                    db.createObjectStore(name, { keyPath: 'id', autoIncrement: true });
                }
            });
        };
        req.onsuccess = e => resolve(e.target.result);
        req.onerror   = e => reject(e.target.error);
    });
}

function enqueue(storeName, payload) {
    return openDB().then(db => new Promise((resolve, reject) => {
        const tx    = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        const req   = store.add({ ...payload, timestamp: Date.now() });
        req.onsuccess = () => resolve(req.result);
        req.onerror   = () => reject(req.error);
    }));
}

function dequeueAll(storeName) {
    return openDB().then(db => new Promise((resolve, reject) => {
        const tx    = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        const items = [];
        const req   = store.openCursor();
        req.onsuccess = e => {
            const cursor = e.target.result;
            if (cursor) {
                items.push(cursor.value);
                store.delete(cursor.primaryKey);
                cursor.continue();
            } else {
                resolve(items);
            }
        };
        req.onerror = () => reject(req.error);
    }));
}

// ── Message handler: page → SW enqueue ───────────────────────────────────────
self.addEventListener('message', event => {
    const { type, store, payload } = event.data || {};
    if (type !== 'ENQUEUE' || !store || !payload) return;

    enqueue(store, payload).then(() => {
        self.registration.sync.register(store).catch(() => {
            // Browser doesn't support Background Sync — flush immediately
            flushQueue(store);
        });
    });
});

// ── Background Sync: replay queued POSTs when back online ────────────────────
self.addEventListener('sync', event => {
    if (STORES.includes(event.tag)) {
        event.waitUntil(flushQueue(event.tag));
    }
});

async function flushQueue(storeName) {
    const items = await dequeueAll(storeName);
    await Promise.all(items.map(item =>
        fetch(item.url, {
            method:  'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body:    item.body,
        }).catch(err => {
            // Re-enqueue on failure so data is never lost
            console.warn('[SW] Replay failed, re-queuing:', err);
            return enqueue(storeName, item);
        })
    ));
}
