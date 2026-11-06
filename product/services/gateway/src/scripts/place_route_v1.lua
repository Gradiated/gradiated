-- Places a generation on one candidate replica and records its lease there.
--
-- KEYS[1] session placement
-- KEYS[2..n+1] per-candidate lease set, in candidate order
-- ARGV[1] generation_id
-- ARGV[2] now, as epoch milliseconds
-- ARGV[3] lease expiry, as epoch milliseconds
-- ARGV[4] session placement lifetime, in milliseconds
-- ARGV[5..] candidate deployment_id and active request limit pairs; 0 is no limit
--
-- Returns {candidate index, outcome}. The outcome is 1 kept on the session's
-- replica, 2 placed a new session, 3 moved from a replica that is no longer a
-- candidate and 4 moved from a full one.

local function fail(message)
  return redis.error_reply('PLACE_ROUTE_V1 ' .. message)
end

local function positive_integer(value, name)
  local number, message = safe_integer(value, name)
  if message then
    return nil, message
  end
  if number <= 0 then
    return nil, name .. ' must be positive'
  end
  return number, nil
end

local candidates = #KEYS - 1
if candidates < 1 or #ARGV ~= 4 + 2 * candidates then
  return fail('expected a session key, one lease key per candidate and matching arguments')
end
if not valid_uuid(ARGV[1]) then
  return fail('generation_id must be a lowercase UUID')
end

local now, now_error = positive_integer(ARGV[2], 'now')
if now_error then return fail(now_error) end
local lease_expiry, expiry_error = positive_integer(ARGV[3], 'lease_expiry')
if expiry_error then return fail(expiry_error) end
local session_lifetime, lifetime_error = positive_integer(ARGV[4], 'session_lifetime')
if lifetime_error then return fail(lifetime_error) end
if lease_expiry <= now then
  return fail('lease_expiry must be later than now')
end

local ids = {}
local limits = {}
local leases = {}
local every_limit_known = true
for index = 1, candidates do
  local id = ARGV[3 + 2 * index]
  if not valid_uuid(id) then
    return fail('deployment_id must be a lowercase UUID')
  end
  local limit, limit_error = safe_integer(ARGV[4 + 2 * index], 'limit')
  if limit_error or limit < 0 then
    return fail('limit must be a non-negative integer')
  end
  local lease_type = redis.call('TYPE', KEYS[1 + index]).ok
  if lease_type ~= 'none' and lease_type ~= 'zset' then
    return fail('lease key is invalid')
  end

  redis.call('ZREMRANGEBYSCORE', KEYS[1 + index], '-inf', now)
  ids[index] = id
  limits[index] = limit
  leases[index] = redis.call('ZCARD', KEYS[1 + index])
  if limit == 0 then
    every_limit_known = false
  end
end

local session_type = redis.call('TYPE', KEYS[1]).ok
if session_type ~= 'none' and session_type ~= 'string' then
  return fail('session key is invalid')
end
local pinned = redis.call('GET', KEYS[1])
local pinned_index = nil
for index = 1, candidates do
  if ids[index] == pinned then
    pinned_index = index
  end
end

local function has_room(index)
  return limits[index] == 0 or leases[index] < limits[index]
end

-- The smaller share of slots in use wins, compared without division. Without
-- every limit, shares are not comparable, so fewer leases wins.
local function better(index, best)
  if every_limit_known then
    return leases[index] * limits[best] < leases[best] * limits[index]
  end
  return leases[index] < leases[best]
end

local chosen
local outcome
if pinned_index and has_room(pinned_index) then
  chosen = pinned_index
  outcome = 1
else
  chosen = 1
  for index = 2, candidates do
    if better(index, chosen) then
      chosen = index
    end
  end
  if pinned_index then
    outcome = 4
  elseif pinned then
    outcome = 3
  else
    outcome = 2
  end
end

redis.call('ZADD', KEYS[1 + chosen], 'NX', lease_expiry, ARGV[1])
redis.call('PEXPIREAT', KEYS[1 + chosen], lease_expiry, 'GT')
if redis.call('PTTL', KEYS[1 + chosen]) < 0 then
  redis.call('PEXPIREAT', KEYS[1 + chosen], lease_expiry)
end
redis.call('SET', KEYS[1], ids[chosen], 'PX', session_lifetime)
return {chosen, outcome}
