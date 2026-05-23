ARG NODE_BASE_IMAGE=node:20-alpine
FROM ${NODE_BASE_IMAGE}

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
