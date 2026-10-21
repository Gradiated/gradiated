FROM golang:1.26.10-bookworm@sha256:fe3da92a5cb2881e4aa75e625cb0b7c50571632fb4cf340cbe53e6ccdcffdd51 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/gpu-controller ./cmd/gpu-controller
RUN CGO_ENABLED=0 go build -trimpath -o /gpu-controller ./cmd/gpu-controller

FROM scratch
COPY --from=build /gpu-controller /gpu-controller
USER 65532:65532
ENTRYPOINT ["/gpu-controller"]
