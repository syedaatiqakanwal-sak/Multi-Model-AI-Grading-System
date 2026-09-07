package proxy

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/gofiber/fiber/v2"
	"gradepro/gateway/internal/auth"
)

var httpClient = &http.Client{
	Timeout: 90 * time.Second,
}

func ProxyTo(targetBaseURL string) fiber.Handler {
	return func(c *fiber.Ctx) error {
		targetURL := fmt.Sprintf("%s%s", targetBaseURL, c.Path())
		if len(c.Request().URI().QueryString()) > 0 {
			targetURL = fmt.Sprintf("%s?%s", targetURL, c.Request().URI().QueryString())
		}

		req, err := http.NewRequest(c.Method(), targetURL, bytes.NewReader(c.Body()))
		if err != nil {
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to create upstream request"})
		}

		// Copy headers
		c.Request().Header.VisitAll(func(k, v []byte) {
			req.Header.Set(string(k), string(v))
		})

		// Inject authenticated user headers
		if claims, ok := c.Locals("user").(*auth.Claims); ok && claims != nil {
			req.Header.Set("X-User-ID", claims.UserID)
			req.Header.Set("X-User-Role", claims.Role)
			req.Header.Set("X-User-Email", claims.Email)
		}

		resp, err := httpClient.Do(req)
		if err != nil {
			return c.Status(fiber.StatusBadGateway).JSON(fiber.Map{"error": "Upstream service unavailable"})
		}
		defer resp.Body.Close()

		respBody, err := io.ReadAll(resp.Body)
		if err != nil {
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": "Failed reading upstream response"})
		}

		for k, v := range resp.Header {
			if len(v) > 0 {
				c.Set(k, v[0])
			}
		}

		return c.Status(resp.StatusCode).Send(respBody)
	}
}
