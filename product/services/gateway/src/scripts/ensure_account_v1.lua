-- Ensures the operational account hash exists and its metadata is current.
--
-- KEYS[1] account hash
-- ARGV[1] organization_id
-- ARGV[2] organization_kind
-- ARGV[3] organization_status
-- ARGV[4] billing_mode
-- ARGV[5] balance, used only when the hash is created
-- ARGV[6] balance_seeded_at, the source balance timestamp the seed included, as epoch milliseconds
-- ARGV[7] metadata_refreshed_at, now, as epoch milliseconds
--
-- Returns 1 when the hash was created and 0 when it already existed. The balance
-- is operational state: it is seeded exactly once and never overwritten here,
-- because settlement has already moved it and PostgreSQL lags behind it.

local account_type = redis.call('TYPE', KEYS[1]).ok
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
    'metadata_refreshed_at', ARGV[7]
  )
  return 1
end

if account_type ~= 'hash' then
  return redis.error_reply('ENSURE_ACCOUNT_V1 gateway account is missing or invalid')
end

redis.call(
  'HSET',
  KEYS[1],
  'organization_id', ARGV[1],
  'organization_kind', ARGV[2],
  'organization_status', ARGV[3],
  'billing_mode', ARGV[4],
  'metadata_refreshed_at', ARGV[7]
)
-- A hash written by anything other than this script carries no watermark. Adopt
-- the source balance timestamp instead of failing, and never move an existing one.
redis.call('HSETNX', KEYS[1], 'balance_seeded_at', ARGV[6])
return 0
