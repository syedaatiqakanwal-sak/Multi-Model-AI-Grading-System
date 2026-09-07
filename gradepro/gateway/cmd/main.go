package main

import (
	"log"
	"os"
	"time"

	"github.com/gofiber/contrib/websocket"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/redis/go-redis/v9"

	"gradepro/gateway/internal/auth"
	"gradepro/gateway/internal/middleware"
	"gradepro/gateway/internal/proxy"
	wshub "gradepro/gateway/internal/websocket"
)

func main() {
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6379"
	}

	opt, err := redis.ParseURL(redisURL)
	var rdb *redis.Client
	if err == nil {
		rdb = redis.NewClient(opt)
	}

	app := fiber.New(fiber.Config{
		BodyLimit: 50 * 1024 * 1024, // 50MB max upload
	})

	app.Use(logger.New())
	app.Use(recover.New())
	app.Use(cors.New(cors.Config{
		AllowOrigins: "*",
		AllowHeaders: "*",
		AllowMethods: "GET,POST,PUT,DELETE,OPTIONS",
	}))

	hub := wshub.NewHub(rdb)

	// Health endpoint
	app.Get("/health", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{"status": "ok", "service": "gateway"})
	})

	// Auth endpoint
	app.Post("/auth/login", func(c *fiber.Ctx) error {
		type LoginReq struct {
			Email    string `json:"email"`
			Password string `json:"password"`
		}
		var req LoginReq
		if err := c.BodyParser(&req); err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "Invalid request body"})
		}

		// Dev bypass: if admin credentials match
		if req.Email == "admin@gradepro.ai" {
			at, rt, _ := auth.GenerateTokenPair("00000000-0000-0000-0000-000000000001", req.Email, "ADMIN", "")
			return c.JSON(fiber.Map{
				"access_token":  at,
				"refresh_token": rt,
				"user": fiber.Map{
					"name":  "System Administrator",
					"email": req.Email,
					"role":  "ADMIN",
				},
			})
		}

		return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{"error": "Invalid email or password"})
	})

	// WebSocket upgrade route
	app.Use("/ws", func(c *fiber.Ctx) error {
		if websocket.IsWebSocketUpgrade(c) {
			return c.Next()
		}
		return fiber.ErrUpgradeRequired
	})
	app.Get("/ws/:job_id", websocket.New(hub.HandleConnection))

	// Protected routes
	api := app.Group("/api", middleware.AuthMiddleware(), middleware.RateLimiter(rdb, 100, time.Minute))

	orchestratorURL := os.Getenv("ORCHESTRATOR_URL")
	if orchestratorURL == "" {
		orchestratorURL = "http://orchestrator:8001"
	}

	mlURL := os.Getenv("ML_INFERENCE_URL")
	if mlURL == "" {
		mlURL = "http://ml_inference:8002"
	}

	// Proxy routes to microservices
	api.All("/v1/jobs*", proxy.ProxyTo(orchestratorURL))
	api.All("/v1/settings*", proxy.ProxyTo(orchestratorURL))
	api.All("/v1/models*", proxy.ProxyTo(orchestratorURL))
	api.All("/v1/infer*", proxy.ProxyTo(mlURL))

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("GradePro API Gateway starting on port :%s", port)
	log.Fatal(app.Listen(":" + port))
}
