FROM node:20-alpine AS builder
RUN apk add --no-cache git
WORKDIR /repo
RUN git clone https://github.com/danielnguyenfinhub/MiroFish.git .
WORKDIR /repo/frontend
RUN npm install
ARG VITE_BACKEND_URL
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /repo/frontend/dist /usr/share/nginx/html
RUN echo 'server { listen 80; root /usr/share/nginx/html; index index.html; location / { try_files $uri $uri/ /index.html; } }' > /etc/nginx/conf.d/default.conf
EXPOSE 80
