-- Admits a generation by adding its lease to the in-flight set.
--
-- KEYS[1] account hash
-- KEYS[2] in-flight lease set
-- KEYS[3] settlement stream
-- ARGV[1] generation_id
-- ARGV[2] organization_id
-- ARGV[3] now, as epoch milliseconds
-- ARGV[4] lease expiry, as epoch milliseconds
-- ARGV[5] cutoff before which expired leases are removed, as epoch milliseconds
-- ARGV[6] organization concurrency cap
-- ARGV[7] prepaid balance per concurrency slot
-- ARGV[8] settlement backlog limit
--
-- Returns 1 admitted, 2 insufficient balance, 3 settlement backlog, 4 concurrency
-- exceeded and 5 duplicate generation.

local function fail(message)
  return redis.error_reply('ADMIT_GENERATION_V1 ' .. message)
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

if #KEYS ~= 3 or #ARGV ~= 8 then
  return fail('expected three keys and eight arguments')
end
if not valid_uuid(ARGV[1]) then
  return fail('generation_id must be a lowercase UUID')
end
if not valid_uuid(ARGV[2]) then
  return fail('organization_id must be a lowercase UUID')
end

local now, numeric_error = positive_integer(ARGV[3], 'now')
if numeric_error then return fail(numeric_error) end
local lease_expiry, expiry_error = positive_integer(ARGV[4], 'lease_expiry')
if expiry_error then return fail(expiry_error) end
local cleanup_cutoff, cutoff_error = positive_integer(ARGV[5], 'cleanup_cutoff')
if cutoff_error then return fail(cutoff_error) end
local concurrency_cap, cap_error = positive_integer(ARGV[6], 'concurrency_cap')
if cap_error then return fail(cap_error) end
local balance_per_slot, slot_error = positive_integer(ARGV[7], 'balance_per_slot')
if slot_error then return fail(slot_error) end
local backlog_limit, backlog_error = positive_integer(ARGV[8], 'backlog_limit')
if backlog_error then return fail(backlog_error) end
if lease_expiry <= now then
  return fail('lease_expiry must be later than now')
end
if cleanup_cutoff > now then
  return fail('cleanup_cutoff cannot be later than now')
end

local account_type = redis.call('TYPE', KEYS[1]).ok
if account_type ~= 'hash' then
  return fail('gateway account is missing or invalid')
end
local inflight_type = redis.call('TYPE', KEYS[2]).ok
if inflight_type ~= 'none' and inflight_type ~= 'zset' then
  return fail('in-flight key is invalid')
end
local stream_type = redis.call('TYPE', KEYS[3]).ok
if stream_type ~= 'none' and stream_type ~= 'stream' then
  return fail('settlement key is invalid')
end

local account = redis.call(
  'HMGET', KEYS[1], 'organization_id', 'organization_status', 'billing_mode', 'balance'
)
if account[1] ~= ARGV[2] then
  return fail('gateway account organization does not match')
end
if account[2] ~= 'active' then
  return fail('organization is not active')
end
if account[3] ~= 'prepaid' and account[3] ~= 'invoiced' then
  return fail('billing_mode is invalid')
end
local balance, balance_error = safe_integer(account[4], 'balance')
if balance_error then return fail(balance_error) end

local backlog = 0
if stream_type == 'stream' then
  backlog = redis.call('XLEN', KEYS[3])
end
if backlog >= backlog_limit then
  return 3
end
if account[3] == 'prepaid' and balance <= 0 then
  return 2
end

redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', '(' .. cleanup_cutoff)

-- Concurrency is a capacity limit, not a billing one, so it applies to every
-- organization. A prepaid balance narrows it further; an invoiced account is
-- capped by the same ceiling rather than being unbounded, because one tenant
-- holding unlimited concurrent generations starves the fleet for everyone.
local active = redis.call('ZCOUNT', KEYS[2], '(' .. now, '+inf')
local selected_limit = concurrency_cap
if account[3] == 'prepaid' then
  local funded_limit = math.floor((balance - 1) / balance_per_slot) + 1
  selected_limit = math.min(concurrency_cap, math.max(20, funded_limit))
end
if active >= selected_limit then
  return 4
end

local added = redis.call('ZADD', KEYS[2], 'NX', lease_expiry, ARGV[1])
if added ~= 1 then
  return 5
end
return 1
