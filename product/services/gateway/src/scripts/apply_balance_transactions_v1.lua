-- Applies ledger entries to the operational balance exactly once.
--
-- KEYS[1] account hash
-- KEYS[2] applied transaction set
-- ARGV[1] the highest entry timestamp in this batch, as epoch milliseconds
-- ARGV[2..] entry id and signed amount, in pairs
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

local applied = 0
for index = 2, #ARGV, 2 do
  if redis.call('SADD', KEYS[2], ARGV[index]) == 1 then
    redis.call('HINCRBY', KEYS[1], 'balance', ARGV[index + 1])
    applied = applied + 1
  end
end

local watermark = tonumber(ARGV[1])
local current = tonumber(redis.call('HGET', KEYS[1], 'balance_seeded_at')) or 0
if watermark and watermark > current then
  redis.call('HSET', KEYS[1], 'balance_seeded_at', watermark)
end

return applied
