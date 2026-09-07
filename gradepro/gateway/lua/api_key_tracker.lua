-- API key daily usage tracker
-- KEYS[1]: apikey:{id}:usage:{YYYY-MM-DD}
-- ARGV[1]: expiry in seconds (e.g. 86400)

local key = KEYS[1]
local ttl = tonumber(ARGV[1]) or 86400

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, ttl)
end

return count
