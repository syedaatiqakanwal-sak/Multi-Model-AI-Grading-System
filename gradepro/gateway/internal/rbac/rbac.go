package rbac

import (
	"github.com/gofiber/fiber/v2"
	"gradepro/gateway/internal/auth"
)

var PermissionMap = map[string][]string{
	"grade:submit":        {"ADMIN", "MAIN_ASSESSOR", "ASSESSOR"},
	"grade:override":      {"ADMIN", "MAIN_ASSESSOR"},
	"records:view_all":    {"ADMIN", "MAIN_ASSESSOR"},
	"records:view_own":    {"ADMIN", "MAIN_ASSESSOR", "ASSESSOR"},
	"templates:upload":    {"ADMIN"},
	"templates:edit":      {"ADMIN", "MAIN_ASSESSOR"},
	"models:retrain":      {"ADMIN"},
	"models:promote":      {"ADMIN"},
	"format_rules:manage": {"ADMIN"},
	"users:manage":        {"ADMIN"},
	"api_keys:manage":     {"ADMIN"},
	"criteria:update":     {"ADMIN"},
}

func RequireRole(allowedRoles ...string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		claims, ok := c.Locals("user").(*auth.Claims)
		if !ok || claims == nil {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"error": "Authentication required",
			})
		}

		for _, role := range allowedRoles {
			if claims.Role == role {
				return c.Next()
			}
		}

		return c.Status(fiber.StatusForbidden).JSON(fiber.Map{
			"error": "Insufficient permissions for this resource",
		})
	}
}
