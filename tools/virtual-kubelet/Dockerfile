FROM golang:1.26.11-bookworm@sha256:dc40a13b61304647ed7e5d581d246b86413dfc29d63c6d018310feb93cd98fc0 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/gpu-controller ./cmd/gpu-controller
RUN CGO_ENABLED=0 go build -trimpath -o /gpu-controller ./cmd/gpu-controller

FROM scratch
COPY --from=build /gpu-controller /gpu-controller
USER 65532:65532
ENTRYPOINT ["/gpu-controller"]
