FROM nginx:alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our custom config
COPY gramsetu.conf /etc/nginx/conf.d/gramsetu.conf

# Expose ports
EXPOSE 80
EXPOSE 443

CMD ["nginx", "-g", "daemon off;"]
