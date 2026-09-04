# ---- build ----
FROM golang:1.26-alpine AS build
WORKDIR /src

# Dependencies first, so source edits do not invalidate the download layer.
COPY go.mod go.sum ./
RUN go mod download

COPY . .
# Static binary: the runtime image has no libc to link against.
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/api ./cmd/api

# ---- runtime ----
FROM alpine:3.22
RUN apk add --no-cache ca-certificates wget \
    && adduser -D -u 10001 stockroom
COPY --from=build /out/api /usr/local/bin/api
USER stockroom
EXPOSE 8080

# wget comes from busybox; the runtime image is alpine rather than distroless
# precisely so compose has something to run this with.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:8080/healthz | grep -q '"status":"ok"' || exit 1

ENTRYPOINT ["/usr/local/bin/api"]
