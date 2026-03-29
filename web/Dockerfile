FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY style.css /usr/share/nginx/html/style.css
COPY app.js /usr/share/nginx/html/app.js
COPY vendor /usr/share/nginx/html/vendor
COPY utils /usr/share/nginx/html/utils
COPY assets /usr/share/nginx/html/assets

EXPOSE 80
