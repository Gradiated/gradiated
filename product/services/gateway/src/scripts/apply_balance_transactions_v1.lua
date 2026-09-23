-- Applies ledger entries to the operational balance exactly once.
--
-- KEYS[1] account hash
-- KEYS[2] applied transaction set
-- ARGV[1] the last applied entry's timestamp, as epoch milliseconds
-- ARGV[2] the last applied entry's id, which breaks ties on that timestamp
-- ARGV[3..] entry id and signed amount, in pairs
--
-- Returns the number of entries this call applied. The set makes a repeated or
-- concurrent call a no-op, and the watermark only ever moves forward, so a
-- gateway running behind another cannot rewind it and replay.

local account_type = redis.call('TYPE', KEYS[1]).ok
if account_type ~= 'hash' then
  return redis.error_reply('APPLY_BALANCE_TRANSACTIONS_V1 gateway account is missing or invalid')
end

local applied_type = redis.call('TYPE', KEYS[2]).ok
if applied_type ~= 'none' and applied_type ~= 'set' then
  return redis.error_reply('APPLY_BALANCE_TRANSACTIONS_V1 applied transaction set is invalid')
end

-- The balance is money and Lua's numbers are doubles, so an amount outside the
-- safe range must be refused rather than silently rounded. Past 2^53 the admission
-- script's own guard would then reject every request for this organization.
local MAX_SAFE_INTEGER = 9007199254740991

local function safe_amount(value)
  if type(value) ~= 'string' or value == '' then
    return nil
  end
  local digits = value
  if string.sub(digits, 1, 1) == '-' then
    digits = string.sub(digits, 2)
  end
  if digits == '' or string.find(digits, '[^0-9]') then
    return nil
  end
  local number = tonumber(value)
  if not number or number ~= math.floor(number) or math.abs(number) > MAX_SAFE_INTEGER then
    return nil
  end
  return number
end

local watermark = safe_amount(ARGV[1])
if not watermark then
  return redis.error_reply('APPLY_BALANCE_TRANSACTIONS_V1 watermark is not a safe integer')
end

local applied = 0
for index = 3, #ARGV, 2 do
  local amount = safe_amount(ARGV[index + 1])
  if not amount then
    return redis.error_reply('APPLY_BALANCE_TRANSACTIONS_V1 amount is not a safe integer')
  end
  if redis.call('SADD', KEYS[2], ARGV[index]) == 1 then
    local balance = safe_amount(redis.call('HGET', KEYS[1], 'balance') or '0')
    if not balance or math.abs(balance + amount) > MAX_SAFE_INTEGER then
      return redis.error_reply('APPLY_BALANCE_TRANSACTIONS_V1 balance would leave the safe range')
    end
    redis.call('HINCRBY', KEYS[1], 'balance', amount)
    applied = applied + 1
  end
end

-- The cursor only moves forward, so a gateway running behind another cannot rewind
-- it and replay. Ties on the timestamp are ordered by the entry id.
local current_at = safe_amount(redis.call('HGET', KEYS[1], 'balance_seeded_at')) or 0
local current_id = redis.call('HGET', KEYS[1], 'balance_seeded_id') or ''
if watermark > current_at or (watermark == current_at and ARGV[2] > current_id) then
  redis.call('HSET', KEYS[1], 'balance_seeded_at', watermark, 'balance_seeded_id', ARGV[2])
end

return applied
