-- Marks the account metadata fresh once its ledger replay has succeeded.
--
-- KEYS[1] account hash
-- ARGV[1] metadata_refreshed_at, now, as epoch milliseconds
--
-- A missing hash is refused rather than recreated with only this field, which
-- would hide the missing balance from the next refresh.

local function fail(message)
  return redis.error_reply('MARK_ACCOUNT_REFRESHED_V1 ' .. message)
end

if #KEYS ~= 1 or #ARGV ~= 1 then
  return fail('expected one key and one argument')
end

local _, refreshed_at_error = safe_integer(ARGV[1], 'metadata_refreshed_at')
if refreshed_at_error then return fail(refreshed_at_error) end

if redis.call('TYPE', KEYS[1]).ok ~= 'hash' then
  return fail('gateway account is missing or invalid')
end

redis.call('HSET', KEYS[1], 'metadata_refreshed_at', ARGV[1])
return 1
