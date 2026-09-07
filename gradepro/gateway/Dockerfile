FROM golang:1.22-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git build-base

COPY . .
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/gateway cmd/main.go

FROM alpine:3.19

WORKDIR /app
RUN apk add --no-cache ca-certificates tzdata curl

COPY --from=builder /app/gateway /app/gateway
COPY ./lua /app/lua

EXPOSE 8080

CMD ["/app/gateway"]
