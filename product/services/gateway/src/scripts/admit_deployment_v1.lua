redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[2])
local existing = redis.call('ZSCORE', KEYS[1], ARGV[1])
if existing then
  return 1
end
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[4]) then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[3], ARGV[1])
redis.call('PEXPIREAT', KEYS[1], ARGV[3])
return 1
