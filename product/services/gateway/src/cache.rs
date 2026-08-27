use std::{
    collections::HashMap,
    future::Future,
    hash::Hash,
    sync::Arc,
    time::{Duration, Instant},
};

use tokio::sync::Mutex;

#[derive(Clone)]
pub struct LazyTtlCache<K, V> {
    ttl: Duration,
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
    pub fn new(ttl: Duration) -> Self {
        Self {
            ttl,
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
        let load_lock = {
            let mut loads = self.loads.lock().await;
            loads
                .entry(key.clone())
                .or_insert_with(|| Arc::new(Mutex::new(())))
                .clone()
        };
        let _load = load_lock.lock().await;
        if let Some(value) = self.get(&key).await {
            return Ok(value);
        }
        let value = load().await?;
        self.values.lock().await.insert(
            key,
            CacheValue {
                loaded_at: Instant::now(),
                value: value.clone(),
            },
        );
        Ok(value)
    }

    async fn get(&self, key: &K) -> Option<V> {
        self.values
            .lock()
            .await
            .get(key)
            .filter(|entry| entry.loaded_at.elapsed() < self.ttl)
            .map(|entry| entry.value.clone())
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use super::*;

    #[tokio::test]
    async fn caches_one_load_for_the_ttl() {
        let cache = LazyTtlCache::new(Duration::from_secs(1));
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
}
