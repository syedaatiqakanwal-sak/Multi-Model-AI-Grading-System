-- Sliding window rate limiter
-- KEYS[1]: rate limit key (e.g. rate:user_id:endpoint)
-- ARGV[1]: current timestamp in milliseconds
-- ARGV[2]: window size in milliseconds
-- ARGV[3]: max allowed requests

local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local clear_before = now - window

-- 1. Remove entries outside current sliding window
redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)

-- 2. Count requests in current window
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    -- 3. Add current request with timestamp score
    redis.call('ZADD', key, now, now)
    redis.call('PEXPIRE', key, window)
    return 1 -- Allowed
else
    return 0 -- Rejected
end
