-- Ensures the operational account hash exists and holds the current metadata.
--
-- KEYS[1] account hash
-- KEYS[2] applied transaction set
-- ARGV[1] organization_id
-- ARGV[2] organization_kind
-- ARGV[3] organization_status
-- ARGV[4] billing_mode
-- ARGV[5] balance, used only when the hash is created
-- ARGV[6] balance_seeded_at, the ledger head the balance includes, as epoch milliseconds
-- ARGV[7] balance_seeded_id, the ledger head's id
-- ARGV[8..] ids of entries the balance includes that a replay from the seeded
--           watermark fetches again, used only when the hash is created
--
-- Returns 1 when the hash was created and 0 when it already existed. The balance
-- is operational state: it is seeded exactly once and never overwritten here,
-- because settlement has already moved it and PostgreSQL lags behind it.
--
-- This never marks the metadata fresh. The caller does that only after the ledger
-- replay succeeds, so a failed replay is retried by the next request instead of
-- hidden for a whole refresh interval.

local function fail(message)
  return redis.error_reply('ENSURE_ACCOUNT_V1 ' .. message)
end

if #KEYS ~= 2 or #ARGV < 7 then
  return fail('expected two keys and at least seven arguments')
end
if not valid_uuid(ARGV[1]) then
  return fail('organization_id must be a lowercase UUID')
end
if not valid_uuid(ARGV[7]) then
  return fail('balance_seeded_id must be a lowercase UUID')
end
for index = 8, #ARGV do
  if not valid_uuid(ARGV[index]) then
    return fail('applied transaction id must be a lowercase UUID')
  end
end

local _, balance_error = safe_integer(ARGV[5], 'balance')
if balance_error then return fail(balance_error) end
local _, seeded_at_error = safe_integer(ARGV[6], 'balance_seeded_at')
if seeded_at_error then return fail(seeded_at_error) end

local account_type = redis.call('TYPE', KEYS[1]).ok
if account_type ~= 'none' and account_type ~= 'hash' then
  return fail('gateway account is invalid')
end
local applied_type = redis.call('TYPE', KEYS[2]).ok
if applied_type ~= 'none' and applied_type ~= 'set' then
  return fail('applied transaction set is invalid')
end

if account_type == 'none' then
  redis.call(
    'HSET',
    KEYS[1],
    'organization_id', ARGV[1],
    'organization_kind', ARGV[2],
    'organization_status', ARGV[3],
    'billing_mode', ARGV[4],
    'balance', ARGV[5],
    'balance_seeded_at', ARGV[6],
    'balance_seeded_id', ARGV[7]
  )
  for index = 8, #ARGV do
    redis.call('SADD', KEYS[2], ARGV[index])
  end
  return 1
end

redis.call(
  'HSET',
  KEYS[1],
  'organization_id', ARGV[1],
  'organization_kind', ARGV[2],
  'organization_status', ARGV[3],
  'billing_mode', ARGV[4]
)
-- A watermark without an id comes from a seed that recorded no replay window,
-- and the apply script may already have advanced it past that seed. The highest
-- id resumes after that whole instant, and the replay floor keeps every later
-- replay window from reaching back to entries the balance already includes.
-- Never move an existing watermark.
redis.call('HSETNX', KEYS[1], 'balance_seeded_at', ARGV[6])
if redis.call('HSETNX', KEYS[1], 'balance_seeded_id', 'ffffffff-ffff-ffff-ffff-ffffffffffff') == 1 then
  redis.call('HSET', KEYS[1], 'balance_replay_floor_at', redis.call('HGET', KEYS[1], 'balance_seeded_at'))
end
return 0
