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
RUN printf 'server {\n  listen $PORT;\n  root /usr/share/nginx/html;\n  index index.html;\n  location / {\n    try_files $uri $uri/ /index.html;\n  }\n}\n' > /tmp/nginx.conf.template
COPY --from=builder /repo/frontend/dist /usr/share/nginx/html
EXPOSE 80
CMD ["sh", "-c", "envsubst '$PORT' < /tmp/nginx.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
