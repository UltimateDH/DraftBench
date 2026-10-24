FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install
COPY . .
EXPOSE 8081
ENV CHOKIDAR_USEPOLLING=true
CMD ["npx", "expo", "start", "--web", "--host", "lan", "--port", "8081"]