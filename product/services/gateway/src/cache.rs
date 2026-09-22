use std::{
    collections::HashMap,
    future::Future,
    hash::Hash,
    sync::Arc,
    time::{Duration, Instant},
};

use tokio::sync::Mutex;

/// A bounded, single-flight cache with a fixed entry lifetime.
///
/// Keys can come from a request, so both maps are capped. Reaching the cap drops
/// elapsed entries first and then the oldest live entry, which stops a caller that
/// asks for many distinct names from growing the process without limit. Negative
/// results are stored like any other value and share the same cap.
#[derive(Clone)]
pub struct LazyTtlCache<K, V> {
    ttl: Duration,
    capacity: usize,
    values: Arc<Mutex<HashMap<K, CacheValue<V>>>>,
    loads: Arc<Mutex<HashMap<K, Arc<Mutex<()>>>>>,
}

struct CacheValue<V> {
    loaded_at: Instant,
    value: V,
}

impl<K, V> LazyTtlCache<K, V>
where
    K: Clone + Eq + Hash,
    V: Clone,
{
    pub fn new(ttl: Duration, capacity: usize) -> Self {
        Self {
            ttl,
            capacity: capacity.max(1),
            values: Arc::new(Mutex::new(HashMap::new())),
            loads: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub async fn get_or_load<E, F, Fut>(&self, key: K, load: F) -> Result<V, E>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<V, E>>,
    {
        if let Some(value) = self.get(&key).await {
            return Ok(value);
        }

        let load_lock = self.load_lock(key.clone()).await;
        let _load = load_lock.lock().await;
        if let Some(value) = self.get(&key).await {
            return Ok(value);
        }

        let value = match load().await {
            Ok(value) => value,
            Err(error) => {
                // A failed load leaves no entry and no lock behind.
                self.loads.lock().await.remove(&key);
                return Err(error);
            }
        };
        self.store(key.clone(), value.clone()).await;
        self.loads.lock().await.remove(&key);

        Ok(value)
    }

    async fn load_lock(&self, key: K) -> Arc<Mutex<()>> {
        let mut loads = self.loads.lock().await;
        if loads.len() >= self.capacity {
            // In-flight loads count toward the cap. A lock no other task holds
            // cannot serialize anything, so it is the one to drop.
            loads.retain(|_, lock| Arc::strong_count(lock) > 1);
        }

        loads.entry(key).or_default().clone()
    }

    async fn store(&self, key: K, value: V) {
        let mut values = self.values.lock().await;
        if values.len() >= self.capacity {
            values.retain(|_, entry| entry.loaded_at.elapsed() < self.ttl);
        }
        if values.len() >= self.capacity {
            let oldest = values
                .iter()
                .min_by_key(|(_, entry)| entry.loaded_at)
                .map(|(key, _)| key.clone());
            if let Some(oldest) = oldest {
                values.remove(&oldest);
            }
        }

        values.insert(
            key,
            CacheValue {
                loaded_at: Instant::now(),
                value,
            },
        );
    }

    async fn get(&self, key: &K) -> Option<V> {
        self.values
            .lock()
            .await
            .get(key)
            .filter(|entry| entry.loaded_at.elapsed() < self.ttl)
            .map(|entry| entry.value.clone())
    }

    #[cfg(test)]
    async fn entries(&self) -> usize {
        self.values.lock().await.len()
    }

    #[cfg(test)]
    async fn in_flight_entries(&self) -> usize {
        self.loads.lock().await.len()
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use super::*;

    #[tokio::test]
    async fn caches_one_load_for_the_ttl() {
        let cache = LazyTtlCache::new(Duration::from_secs(1), 10);
        let loads = AtomicUsize::new(0);
        for _ in 0..2 {
            let value = cache
                .get_or_load("key", || async {
                    loads.fetch_add(1, Ordering::SeqCst);
                    Ok::<_, ()>(42)
                })
                .await
                .unwrap();
            assert_eq!(value, 42);
        }
        assert_eq!(loads.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn distinct_keys_never_exceed_the_capacity() {
        let cache = LazyTtlCache::new(Duration::from_secs(60), 8);
        for key in 0..500 {
            cache
                .get_or_load(key, || async { Ok::<_, ()>(key) })
                .await
                .unwrap();
        }

        assert_eq!(cache.entries().await, 8);
        assert_eq!(
            cache.in_flight_entries().await,
            0,
            "a completed load leaves no lock behind"
        );
    }

    #[tokio::test]
    async fn a_missing_record_is_cached_once_and_stays_bounded() {
        let cache = LazyTtlCache::new(Duration::from_secs(60), 4);
        let loads = AtomicUsize::new(0);
        for _ in 0..2 {
            let value: Option<u32> = cache
                .get_or_load("missing".to_owned(), || async {
                    loads.fetch_add(1, Ordering::SeqCst);
                    Ok::<_, ()>(None)
                })
                .await
                .unwrap();
            assert_eq!(value, None);
        }
        assert_eq!(loads.load(Ordering::SeqCst), 1);

        for key in 0..64 {
            cache
                .get_or_load(key.to_string(), || async { Ok::<_, ()>(None) })
                .await
                .unwrap();
        }
        assert_eq!(cache.entries().await, 4);
    }

    #[tokio::test]
    async fn an_elapsed_entry_is_reloaded_and_replaced() {
        let cache = LazyTtlCache::new(Duration::from_millis(20), 4);
        let loads = AtomicUsize::new(0);
        for _ in 0..2 {
            cache
                .get_or_load("key", || async {
                    loads.fetch_add(1, Ordering::SeqCst);
                    Ok::<_, ()>(7)
                })
                .await
                .unwrap();
            tokio::time::sleep(Duration::from_millis(30)).await;
        }

        assert_eq!(loads.load(Ordering::SeqCst), 2);
        assert_eq!(cache.entries().await, 1);
    }

    #[tokio::test]
    async fn a_failed_load_caches_nothing() {
        let cache = LazyTtlCache::new(Duration::from_secs(60), 4);
        let result: Result<u32, &str> = cache.get_or_load("key", || async { Err("down") }).await;

        assert_eq!(result, Err("down"));
        assert_eq!(cache.entries().await, 0);
        assert_eq!(cache.in_flight_entries().await, 0);
    }
}
