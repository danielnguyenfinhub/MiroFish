FROM node:20-alpine AS builder
RUN apk add --no-cache git
WORKDIR /repo
RUN git clone https://github.com/danielnguyenfinhub/MiroFish.git .
WORKDIR /repo/frontend
RUN npm install
ARG VITE_BACKEND_URL
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL
RUN npm run build

FROM node:20-alpine
RUN npm install -g serve
WORKDIR /app
COPY --from=builder /repo/frontend/dist ./dist
EXPOSE 3000
CMD ["serve", "-s", "dist", "-l", "$PORT"]
