-- Admits an eval-lane generation under its workspace's eval limits.
--
-- KEYS[1] the workspace's in-flight eval set: generation_id scored by lease expiry
-- KEYS[2] the workspace's eval request count for the current minute
-- ARGV[1] generation_id
-- ARGV[2] now, as epoch milliseconds
-- ARGV[3] lease expiry, as epoch milliseconds
-- ARGV[4] concurrency cap
-- ARGV[5] requests per minute
--
-- Returns 1 admitted, 2 concurrency cap reached and 3 per-minute cap reached.

local function fail(message)
  return redis.error_reply('ADMIT_EVAL_V1 ' .. message)
end

if #KEYS ~= 2 or #ARGV ~= 5 then
  return fail('expected two keys and five arguments')
end
if not valid_uuid(ARGV[1]) then
  return fail('generation_id must be a lowercase UUID')
end

local now, now_error = safe_integer(ARGV[2], 'now')
if now_error then return fail(now_error) end
local lease_expiry, expiry_error = safe_integer(ARGV[3], 'lease_expiry')
if expiry_error then return fail(expiry_error) end
local concurrency_cap, cap_error = safe_integer(ARGV[4], 'concurrency_cap')
if cap_error then return fail(cap_error) end
local per_minute, rate_error = safe_integer(ARGV[5], 'per_minute')
if rate_error then return fail(rate_error) end
if lease_expiry <= now or concurrency_cap <= 0 or per_minute <= 0 then
  return fail('limits and lease expiry must be positive and in the future')
end

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= concurrency_cap then
  return 2
end

local count = redis.call('INCR', KEYS[2])
if count == 1 then
  redis.call('PEXPIRE', KEYS[2], 120000)
end
if count > per_minute then
  return 3
end

redis.call('ZADD', KEYS[1], lease_expiry, ARGV[1])
if redis.call('PTTL', KEYS[1]) < lease_expiry - now + 60000 then
  redis.call('PEXPIREAT', KEYS[1], lease_expiry + 60000)
end
return 1
