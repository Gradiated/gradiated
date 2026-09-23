-- Applies ledger entries to the operational balance exactly once.
--
-- KEYS[1] account hash
-- KEYS[2] applied transaction set
-- ARGV[1] the last applied entry's timestamp, as epoch milliseconds
-- ARGV[2] the last applied entry's id, which breaks ties on that timestamp
-- ARGV[3..] entry id and signed amount, in pairs
--
-- Returns the number of entries this call applied. The whole batch is validated
-- before the first write, so a refused batch changes nothing. The set makes a
-- repeated or concurrent call a no-op, and the watermark only ever moves forward,
-- so a gateway running behind another cannot rewind it and replay.

local function fail(message)
  return redis.error_reply('APPLY_BALANCE_TRANSACTIONS_V1 ' .. message)
end

if #KEYS ~= 2 or #ARGV < 2 or #ARGV % 2 ~= 0 then
  return fail('expected two keys and an even number of arguments')
end

local watermark, watermark_error = safe_integer(ARGV[1], 'watermark')
if watermark_error then return fail(watermark_error) end
if not valid_uuid(ARGV[2]) then
  return fail('watermark id must be a lowercase UUID')
end

local account_type = redis.call('TYPE', KEYS[1]).ok
if account_type ~= 'hash' then
  return fail('gateway account is missing or invalid')
end
local applied_type = redis.call('TYPE', KEYS[2]).ok
if applied_type ~= 'none' and applied_type ~= 'set' then
  return fail('applied transaction set is invalid')
end

local balance, balance_error = safe_integer(redis.call('HGET', KEYS[1], 'balance'), 'balance')
if balance_error then return fail(balance_error) end

local pending = {}
local seen = {}
for index = 3, #ARGV, 2 do
  local id = ARGV[index]
  if not valid_uuid(id) then
    return fail('transaction id must be a lowercase UUID')
  end
  local amount, amount_error = safe_integer(ARGV[index + 1], 'amount')
  if amount_error then return fail(amount_error) end
  if not seen[id] and redis.call('SISMEMBER', KEYS[2], id) == 0 then
    balance = balance + amount
    if math.abs(balance) > MAX_SAFE_INTEGER then
      return fail('balance would leave the safe range')
    end
    pending[#pending + 1] = { id = id, amount = ARGV[index + 1] }
  end
  seen[id] = true
end

for _, entry in ipairs(pending) do
  redis.call('SADD', KEYS[2], entry.id)
  redis.call('HINCRBY', KEYS[1], 'balance', entry.amount)
end

local current_at = safe_integer(redis.call('HGET', KEYS[1], 'balance_seeded_at'), 'balance_seeded_at') or 0
local current_id = redis.call('HGET', KEYS[1], 'balance_seeded_id') or ''
if watermark > current_at or (watermark == current_at and ARGV[2] > current_id) then
  redis.call('HSET', KEYS[1], 'balance_seeded_at', watermark, 'balance_seeded_id', ARGV[2])
end

return #pending
