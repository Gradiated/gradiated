local MAX_SAFE_INTEGER = 9007199254740991

local function fail(message)
  return redis.error_reply('FINALIZATION_V1 ' .. message)
end

local function safe_integer(value, name, nonnegative)
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
  if nonnegative and number < 0 then
    return nil, name .. ' must be nonnegative'
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

if #KEYS ~= 3 or #ARGV ~= 4 then
  return fail('expected three keys and four arguments')
end
if not valid_uuid(ARGV[1]) then
  return fail('generation_id must be a lowercase UUID')
end
if not valid_uuid(ARGV[2]) then
  return fail('organization_id must be a lowercase UUID')
end

local charge, charge_error = safe_integer(ARGV[3], 'charge', true)
if charge_error then return fail(charge_error) end
if type(ARGV[4]) ~= 'string' or ARGV[4] == '' then
  return fail('properties must be nonempty JSON')
end
local properties_ok, properties = pcall(cjson.decode, ARGV[4])
if not properties_ok or type(properties) ~= 'table' then
  return fail('properties must be a JSON object')
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

local account = redis.call('HMGET', KEYS[1], 'organization_id', 'balance')
if account[1] ~= ARGV[2] then
  return fail('gateway account organization does not match')
end
local balance, balance_error = safe_integer(account[2], 'balance', false)
if balance_error then return fail(balance_error) end
local updated_balance = balance - charge
if math.abs(updated_balance) > MAX_SAFE_INTEGER then
  return fail('updated balance is outside the safe integer range')
end

local removed = redis.call('ZREM', KEYS[2], ARGV[1])
if removed == 0 then
  return 2
end
redis.call('HSET', KEYS[1], 'balance', string.format('%.0f', updated_balance))
redis.call(
  'XADD', KEYS[3], '*', 'generation_id', ARGV[1], 'properties', ARGV[4]
)
return 1
