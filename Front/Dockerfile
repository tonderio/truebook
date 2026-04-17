FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

# Set API URL before copying source so Vite picks it up
ENV VITE_API_URL=https://truebook-production.up.railway.app/api

COPY . .

# Cache buster — change this to force rebuild
ARG CACHEBUST=2
RUN npm run build

RUN npm install express@4

EXPOSE 3000
CMD ["node", "server.js"]
