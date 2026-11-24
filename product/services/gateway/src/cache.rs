use std::{
    collections::HashMap,
    future::Future,
    hash::Hash,
    sync::{Arc, Mutex, MutexGuard, PoisonError},
    time::{Duration, Instant},
};

/// A bounded, single-flight cache with a fixed entry lifetime.
///
/// Elapsed entries are removed only when the map reaches its capacity, so the cap
/// is what bounds memory as keys come and go. Reaching it drops elapsed entries
/// first and then the oldest live entry.
#[derive(Clone)]
pub struct LazyTtlCache<K, V> {
    ttl: Duration,
    capacity: usize,
    values: Arc<Mutex<HashMap<K, CacheValue<V>>>>,
    loads: SingleFlight<K>,
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
            loads: SingleFlight::default(),
        }
    }

    pub async fn get_or_load<E, F, Fut>(&self, key: K, load: F) -> Result<V, E>
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<V, E>>,
    {
        if let Some(value) = self.get(&key) {
            return Ok(value);
        }

        self.loads
            .run(key.clone(), || async {
                if let Some(value) = self.get(&key) {
                    return Ok(value);
                }

                let value = load().await?;
                self.store(key.clone(), value.clone());

                Ok(value)
            })
            .await
    }

    pub(crate) fn store(&self, key: K, value: V) {
        let mut values = locked(&self.values);
        let entry = CacheValue {
            loaded_at: Instant::now(),
            value,
        };
        if let Some(existing) = values.get_mut(&key) {
            *existing = entry;
            return;
        }

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

        values.insert(key, entry);
    }

    pub(crate) fn get(&self, key: &K) -> Option<V> {
        locked(&self.values)
            .get(key)
            .filter(|entry| entry.loaded_at.elapsed() < self.ttl)
            .map(|entry| entry.value.clone())
    }

    #[cfg(test)]
    fn entries(&self) -> usize {
        locked(&self.values).len()
    }

    #[cfg(test)]
    fn in_flight_entries(&self) -> usize {
        self.loads.in_flight()
    }
}

/// Runs at most one task per key at a time; the others wait for it and then run
/// their own, which should first look for what the finished one produced.
#[derive(Clone)]
pub struct SingleFlight<K> {
    locks: Arc<Mutex<HashMap<K, Arc<tokio::sync::Mutex<()>>>>>,
}

impl<K> SingleFlight<K>
where
    K: Clone + Eq + Hash,
{
    pub async fn run<T, F, Fut>(&self, key: K, task: F) -> T
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = T>,
    {
        let flight = self.join(key);
        let _running = flight.lock.lock().await;

        task().await
    }

    fn join(&self, key: K) -> Flight<'_, K> {
        let lock = locked(&self.locks).entry(key.clone()).or_default().clone();

        Flight {
            locks: &self.locks,
            key,
            lock,
        }
    }

    #[cfg(test)]
    fn in_flight(&self) -> usize {
        locked(&self.locks).len()
    }
}

impl<K> Default for SingleFlight<K>
where
    K: Clone + Eq + Hash,
{
    fn default() -> Self {
        Self {
            locks: Arc::new(Mutex::new(HashMap::new())),
        }
    }
}

/// Leaves the lock in the map while another task still holds a clone of it, so a
/// caller that arrives meanwhile queues behind that task rather than beside it.
/// Dropping also covers a cancelled task.
struct Flight<'a, K: Eq + Hash> {
    locks: &'a Mutex<HashMap<K, Arc<tokio::sync::Mutex<()>>>>,
    key: K,
    lock: Arc<tokio::sync::Mutex<()>>,
}

impl<K: Eq + Hash> Drop for Flight<'_, K> {
    fn drop(&mut self) {
        let mut locks = locked(self.locks);
        let only_this_task = locks
            .get(&self.key)
            .is_some_and(|lock| Arc::ptr_eq(lock, &self.lock) && Arc::strong_count(lock) == 2);
        if only_this_task {
            locks.remove(&self.key);
        }
    }
}

/// Only for state that every critical section leaves consistent, so that a
/// poisoned lock is safe to reuse.
pub(crate) fn locked<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(PoisonError::into_inner)
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use tokio::{sync::Notify, task::JoinSet};

    use super::*;

    async fn let_waiting_tasks_run() {
        for _ in 0..32 {
            tokio::task::yield_now().await;
        }
    }

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

    #[test]
    fn replacing_an_entry_in_a_full_cache_preserves_other_entries() {
        let cache = LazyTtlCache::new(Duration::from_secs(60), 2);
        cache.store("another session", 1);
        cache.store("active session", 2);

        cache.store("active session", 3);

        assert_eq!(cache.get(&"another session"), Some(1));
        assert_eq!(cache.get(&"active session"), Some(3));
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

        assert_eq!(cache.entries(), 8);
        assert_eq!(
            cache.in_flight_entries(),
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
        assert_eq!(cache.entries(), 4);
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
        assert_eq!(cache.entries(), 1);
    }

    #[tokio::test]
    async fn a_failed_load_caches_nothing() {
        let cache = LazyTtlCache::new(Duration::from_secs(60), 4);
        let result: Result<u32, &str> = cache.get_or_load("key", || async { Err("down") }).await;

        assert_eq!(result, Err("down"));
        assert_eq!(cache.entries(), 0);
        assert_eq!(cache.in_flight_entries(), 0);
    }

    #[tokio::test]
    async fn concurrent_callers_share_one_load() {
        let cache = LazyTtlCache::new(Duration::from_secs(60), 4);
        let loads = Arc::new(AtomicUsize::new(0));
        let release = Arc::new(Notify::new());
        let mut callers = JoinSet::new();
        for _ in 0..16 {
            let (cache, loads, release) = (cache.clone(), loads.clone(), release.clone());
            callers.spawn(async move {
                cache
                    .get_or_load("key", || async {
                        loads.fetch_add(1, Ordering::SeqCst);
                        release.notified().await;
                        Ok::<_, ()>(42)
                    })
                    .await
            });
        }

        let_waiting_tasks_run().await;
        assert_eq!(loads.load(Ordering::SeqCst), 1);
        release.notify_one();

        let mut values = Vec::new();
        while let Some(result) = callers.join_next().await {
            values.push(result.unwrap());
        }
        assert_eq!(values, vec![Ok(42); 16]);
        assert_eq!(loads.load(Ordering::SeqCst), 1);
        assert_eq!(cache.in_flight_entries(), 0);
    }

    #[tokio::test]
    async fn a_waiter_retries_after_a_failed_load() {
        let cache = LazyTtlCache::new(Duration::from_secs(60), 4);
        let loads = Arc::new(AtomicUsize::new(0));
        let release = Arc::new(Notify::new());
        let first = tokio::spawn({
            let (cache, loads, release) = (cache.clone(), loads.clone(), release.clone());
            async move {
                cache
                    .get_or_load("key", || async {
                        loads.fetch_add(1, Ordering::SeqCst);
                        release.notified().await;
                        Err("down")
                    })
                    .await
            }
        });
        let_waiting_tasks_run().await;
        let second = tokio::spawn({
            let (cache, loads) = (cache.clone(), loads.clone());
            async move {
                cache
                    .get_or_load("key", || async {
                        loads.fetch_add(1, Ordering::SeqCst);
                        Ok::<_, &str>(7)
                    })
                    .await
            }
        });

        let_waiting_tasks_run().await;
        assert_eq!(loads.load(Ordering::SeqCst), 1);
        release.notify_one();

        assert_eq!(first.await.unwrap(), Err("down"));
        assert_eq!(second.await.unwrap(), Ok(7));
        assert_eq!(loads.load(Ordering::SeqCst), 2);
        assert_eq!(cache.entries(), 1);
        assert_eq!(cache.in_flight_entries(), 0);
    }

    #[tokio::test]
    async fn a_caller_arriving_after_a_failed_load_queues_behind_the_retry() {
        let cache = LazyTtlCache::new(Duration::from_secs(60), 4);
        let running = Arc::new(AtomicUsize::new(0));
        let most_running = Arc::new(AtomicUsize::new(0));
        let release = Arc::new(Notify::new());
        let spawn_caller = |result: Result<u32, &'static str>| {
            let (cache, running, most_running, release) = (
                cache.clone(),
                running.clone(),
                most_running.clone(),
                release.clone(),
            );
            tokio::spawn(async move {
                cache
                    .get_or_load("key", || async {
                        let now_running = running.fetch_add(1, Ordering::SeqCst) + 1;
                        most_running.fetch_max(now_running, Ordering::SeqCst);
                        release.notified().await;
                        running.fetch_sub(1, Ordering::SeqCst);
                        result
                    })
                    .await
            })
        };

        let first = spawn_caller(Err("down"));
        let_waiting_tasks_run().await;
        let second = spawn_caller(Err("still down"));
        let_waiting_tasks_run().await;
        release.notify_one();
        assert_eq!(first.await.unwrap(), Err("down"));

        let_waiting_tasks_run().await;
        let third = spawn_caller(Ok(7));
        let_waiting_tasks_run().await;
        assert_eq!(running.load(Ordering::SeqCst), 1);
        release.notify_one();
        assert_eq!(second.await.unwrap(), Err("still down"));
        let_waiting_tasks_run().await;
        release.notify_one();

        assert_eq!(third.await.unwrap(), Ok(7));
        assert_eq!(most_running.load(Ordering::SeqCst), 1);
        assert_eq!(cache.in_flight_entries(), 0);
    }

    #[tokio::test]
    async fn a_cancelled_load_releases_its_key() {
        let cache = LazyTtlCache::new(Duration::from_secs(60), 4);
        let pending = tokio::spawn({
            let cache = cache.clone();
            async move {
                cache
                    .get_or_load("key", std::future::pending::<Result<u32, ()>>)
                    .await
            }
        });
        let_waiting_tasks_run().await;
        assert_eq!(cache.in_flight_entries(), 1);

        pending.abort();
        let _ = pending.await;

        assert_eq!(cache.in_flight_entries(), 0);
        assert_eq!(
            cache.get_or_load("key", || async { Ok::<_, ()>(7) }).await,
            Ok(7)
        );
    }
}
