package middleware

import (
	"context"
	"fmt"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/redis/go-redis/v9"
	"gradepro/gateway/internal/auth"
)

var rateLimiterScript = redis.NewScript(`
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local clear_before = now - window

redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    redis.call('ZADD', key, now, now)
    redis.call('PEXPIRE', key, window)
    return 1
else
    return 0
end
`)

func RateLimiter(rdb *redis.Client, maxRequests int, window time.Duration) fiber.Handler {
	return func(c *fiber.Ctx) error {
		if rdb == nil {
			return c.Next()
		}

		userKey := c.IP()
		if claims, ok := c.Locals("user").(*auth.Claims); ok && claims != nil {
			userKey = claims.UserID
		}

		key := fmt.Sprintf("rate:%s:%s", userKey, c.Path())
		now := time.Now().UnixMilli()
		windowMs := window.Milliseconds()

		ctx := context.Background()
		res, err := rateLimiterScript.Run(ctx, rdb, []string{key}, now, windowMs, maxRequests).Int()
		if err != nil || res == 0 {
			return c.Status(fiber.StatusTooManyRequests).JSON(fiber.Map{
				"error": "Rate limit exceeded. Please wait a moment.",
			})
		}

		return c.Next()
	}
}
