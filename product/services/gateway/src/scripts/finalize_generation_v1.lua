-- Settles a generation: consumes its lease, debits the charge and appends the
-- settlement event. Every input and key is validated before the first write, and
-- the ZREM guards the debit, so a generation is charged at most once.
--
-- KEYS[1] account hash
-- KEYS[2] in-flight lease set
-- KEYS[3] settlement stream
-- ARGV[1] generation_id
-- ARGV[2] organization_id
-- ARGV[3] charge
-- ARGV[4] generation properties, as a JSON object
--
-- Returns 1 settled and 2 when the lease was already absent.

local function fail(message)
  return redis.error_reply('FINALIZE_GENERATION_V1 ' .. message)
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

local charge, charge_error = safe_integer(ARGV[3], 'charge')
if charge_error then return fail(charge_error) end
if charge < 0 then return fail('charge must be nonnegative') end
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
local balance, balance_error = safe_integer(account[2], 'balance')
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
