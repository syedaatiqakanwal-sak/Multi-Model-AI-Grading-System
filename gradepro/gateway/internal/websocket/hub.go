package websocket

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/gofiber/contrib/websocket"
	"github.com/redis/go-redis/v9"
)

type Hub struct {
	rdb   *redis.Client
	rooms map[string]map[*websocket.Conn]bool
	mu    sync.RWMutex
}

func NewHub(rdb *redis.Client) *Hub {
	return &Hub{
		rdb:   rdb,
		rooms: make(map[string]map[*websocket.Conn]bool),
	}
}

func (h *Hub) HandleConnection(c *websocket.Conn) {
	jobID := c.Params("job_id")
	if jobID == "" {
		c.Close()
		return
	}

	h.mu.Lock()
	if _, ok := h.rooms[jobID]; !ok {
		h.rooms[jobID] = make(map[*websocket.Conn]bool)
		// Start a Redis Stream consumer for this room if first connection
		go h.consumeJobStream(jobID)
	}
	h.rooms[jobID][c] = true
	h.mu.Unlock()

	defer func() {
		h.mu.Lock()
		delete(h.rooms[jobID], c)
		if len(h.rooms[jobID]) == 0 {
			delete(h.rooms, jobID)
		}
		h.mu.Unlock()
		c.Close()
	}()

	// Keep alive & read client messages (e.g. heartbeat)
	for {
		_, _, err := c.ReadMessage()
		if err != nil {
			break
		}
	}
}

func (h *Hub) consumeJobStream(jobID string) {
	if h.rdb == nil {
		return
	}

	streamKey := fmt.Sprintf("job:%s:events", jobID)
	lastID := "0-0"
	ctx := context.Background()

	for {
		h.mu.RLock()
		clientCount := len(h.rooms[jobID])
		h.mu.RUnlock()

		if clientCount == 0 {
			// Room closed, terminate stream reader
			break
		}

		res, err := h.rdb.XRead(ctx, &redis.XReadArgs{
			Streams: []string{streamKey, lastID},
			Count:   10,
			Block:   2 * time.Second,
		}).Result()

		if err != nil || len(res) == 0 {
			continue
		}

		for _, stream := range res {
			for _, msg := range stream.Messages {
				lastID = msg.ID
				msgData, _ := json.Marshal(msg.Values)

				h.mu.RLock()
				for conn := range h.rooms[jobID] {
					if err := conn.WriteMessage(websocket.TextMessage, msgData); err != nil {
						log.Printf("WebSocket write error: %v", err)
					}
				}
				h.mu.RUnlock()
			}
		}
	}
}
