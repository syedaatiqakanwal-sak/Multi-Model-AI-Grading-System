-- Distributed Lock Acquisition (SET NX PX)
-- KEYS[1]: lock key (e.g. lock:model_promote:unit_id)
-- ARGV[1]: lock token/owner
-- ARGV[2]: ttl in milliseconds

local key = KEYS[1]
local token = ARGV[1]
local ttl = tonumber(ARGV[2])

local ok = redis.call('SET', key, token, 'NX', 'PX', ttl)
if ok then
    return 1
else
    return 0
end
