local MAX_SAFE_INTEGER = 9007199254740991

local function fail(message)
  return redis.error_reply('ADMISSION_V1 ' .. message)
end

local function safe_integer(value, name, positive)
  if type(value) ~= 'string' or value == '' then
    return nil, name .. ' must be an integer'
  end
  local digits = value
  if string.sub(digits, 1, 1) == '-' then
    digits = string.sub(digits, 2)
  end
  if digits == '' or string.find(digits, '[^0-9]') then
    return nil, name .. ' must be an integer'
  end
  local number = tonumber(value)
  if not number or number ~= math.floor(number) or math.abs(number) > MAX_SAFE_INTEGER then
    return nil, name .. ' is outside the safe integer range'
  end
  if positive and number <= 0 then
    return nil, name .. ' must be positive'
  end
  return number, nil
end

local function valid_uuid(value)
  if type(value) ~= 'string' or #value ~= 36 then
    return false
  end
  if string.sub(value, 9, 9) ~= '-' or string.sub(value, 14, 14) ~= '-' or
      string.sub(value, 19, 19) ~= '-' or string.sub(value, 24, 24) ~= '-' then
    return false
  end
  local compact, separators = string.gsub(value, '-', '')
  return separators == 4 and #compact == 32 and not string.find(compact, '[^0-9a-f]')
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

local now, numeric_error = safe_integer(ARGV[3], 'now', true)
if numeric_error then return fail(numeric_error) end
local lease_expiry, expiry_error = safe_integer(ARGV[4], 'lease_expiry', true)
if expiry_error then return fail(expiry_error) end
local cleanup_cutoff, cutoff_error = safe_integer(ARGV[5], 'cleanup_cutoff', true)
if cutoff_error then return fail(cutoff_error) end
local prepaid_cap, cap_error = safe_integer(ARGV[6], 'prepaid_cap', true)
if cap_error then return fail(cap_error) end
local balance_per_slot, slot_error = safe_integer(ARGV[7], 'balance_per_slot', true)
if slot_error then return fail(slot_error) end
local backlog_limit, backlog_error = safe_integer(ARGV[8], 'backlog_limit', true)
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
local balance, balance_error = safe_integer(account[4], 'balance', false)
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

if account[3] == 'prepaid' then
  local active = redis.call('ZCOUNT', KEYS[2], '(' .. now, '+inf')
  local funded_limit = math.floor((balance - 1) / balance_per_slot) + 1
  local selected_limit = math.min(prepaid_cap, funded_limit)
  if active >= selected_limit then
    return 4
  end
end

local added = redis.call('ZADD', KEYS[2], 'NX', lease_expiry, ARGV[1])
if added ~= 1 then
  return 5
end
return 1
