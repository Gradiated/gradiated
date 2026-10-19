FROM golang:1.26.9-bookworm@sha256:d9c68c2c51161e12fd77e4c6320687c9cd86e1af1e3ad6e6cd63ff970641453c AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/gpu-controller ./cmd/gpu-controller
RUN CGO_ENABLED=0 go build -trimpath -o /gpu-controller ./cmd/gpu-controller

FROM scratch
COPY --from=build /gpu-controller /gpu-controller
USER 65532:65532
ENTRYPOINT ["/gpu-controller"]
