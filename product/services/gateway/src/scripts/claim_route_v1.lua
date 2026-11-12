-- Moves a session to the replica a generation fell back to, and records its
-- lease there.
--
-- KEYS[1] session placement
-- KEYS[2] the replica's lease set
-- ARGV[1] generation_id
-- ARGV[2] deployment_id
-- ARGV[3] now, as epoch milliseconds
-- ARGV[4] lease expiry, as epoch milliseconds
-- ARGV[5] session placement lifetime, in milliseconds

local function fail(message)
  return redis.error_reply('CLAIM_ROUTE_V1 ' .. message)
end

if #KEYS ~= 2 or #ARGV ~= 5 then
  return fail('expected two keys and five arguments')
end
if not valid_uuid(ARGV[1]) then
  return fail('generation_id must be a lowercase UUID')
end
if not valid_uuid(ARGV[2]) then
  return fail('deployment_id must be a lowercase UUID')
end

local now, now_error = safe_integer(ARGV[3], 'now')
if now_error then return fail(now_error) end
local lease_expiry, expiry_error = safe_integer(ARGV[4], 'lease_expiry')
if expiry_error then return fail(expiry_error) end
local session_lifetime, lifetime_error = safe_integer(ARGV[5], 'session_lifetime')
if lifetime_error then return fail(lifetime_error) end
if lease_expiry <= now or session_lifetime <= 0 then
  return fail('lease_expiry and session_lifetime must be in the future')
end

local session_type = redis.call('TYPE', KEYS[1]).ok
if session_type ~= 'none' and session_type ~= 'string' then
  return fail('session key is invalid')
end
local lease_type = redis.call('TYPE', KEYS[2]).ok
if lease_type ~= 'none' and lease_type ~= 'zset' then
  return fail('lease key is invalid')
end

redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
redis.call('ZADD', KEYS[2], 'NX', lease_expiry, ARGV[1])
redis.call('PEXPIREAT', KEYS[2], lease_expiry, 'GT')
if redis.call('PTTL', KEYS[2]) < 0 then
  redis.call('PEXPIREAT', KEYS[2], lease_expiry)
end
redis.call('SET', KEYS[1], ARGV[2], 'PX', session_lifetime)
return 1
