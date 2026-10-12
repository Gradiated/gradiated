FROM golang:1.24.13-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/kev-controller ./cmd/kev-controller
RUN CGO_ENABLED=0 go build -trimpath -o /gpu-controller ./cmd/kev-controller

FROM scratch
COPY --from=build /gpu-controller /gpu-controller
USER 65532:65532
ENTRYPOINT ["/gpu-controller"]
