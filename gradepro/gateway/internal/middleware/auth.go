package middleware

import (
	"strings"

	"github.com/gofiber/fiber/v2"
	"gradepro/gateway/internal/auth"
)

func AuthMiddleware() fiber.Handler {
	return func(c *fiber.Ctx) error {
		authHeader := c.Get("Authorization")
		if authHeader == "" {
			// In development, default to mock admin if no header provided
			c.Locals("user", &auth.Claims{
				UserID: "00000000-0000-0000-0000-000000000001",
				Email:  "admin@gradepro.ai",
				Role:   "ADMIN",
			})
			return c.Next()
		}

		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || parts[0] != "Bearer" {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"error": "Invalid authorization header format",
			})
		}

		claims, err := auth.ValidateToken(parts[1])
		if err != nil {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"error": "Invalid or expired token",
			})
		}

		c.Locals("user", claims)
		return c.Next()
	}
}
