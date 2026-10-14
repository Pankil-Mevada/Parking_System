FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587 AS build
COPY backend/build-packages.lock /tmp/packages.lock
RUN apt-get update && tr -d '\r' < /tmp/packages.lock | xargs apt-get install -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
RUN git clone --branch v1.9.14 --depth 1 --recurse-submodules --shallow-submodules https://github.com/drogonframework/drogon.git /tmp/drogon
RUN test "$(git -C /tmp/drogon rev-parse HEAD)" = "3aae769cc405cf5abb9d477675c6430924f02c7c"
RUN cmake -S /tmp/drogon -B /tmp/drogon-build -DCMAKE_BUILD_TYPE=Release -DBUILD_EXAMPLES=OFF -DBUILD_CTL=OFF -DBUILD_TESTING=OFF -DBUILD_MYSQL=OFF -DBUILD_SQLITE=OFF -DBUILD_REDIS=OFF -DBUILD_POSTGRESQL=ON && cmake --build /tmp/drogon-build -j2 && cmake --install /tmp/drogon-build
WORKDIR /src
COPY backend/ ./
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j2
RUN dpkg-query -W '-f=${binary:Package}=${Version}\n' | sort > /tmp/installed.lock && tr -d '\r' < /tmp/packages.lock | sort > /tmp/expected.lock && diff -u /tmp/expected.lock /tmp/installed.lock
FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587
COPY backend/runtime-packages.lock /tmp/packages.lock
RUN apt-get update && tr -d '\r' < /tmp/packages.lock | xargs apt-get install -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/parking_api /usr/local/bin/parking_api
RUN dpkg-query -W '-f=${binary:Package}=${Version}\n' | sort > /tmp/installed.lock && tr -d '\r' < /tmp/packages.lock | sort > /tmp/expected.lock && diff -u /tmp/expected.lock /tmp/installed.lock
RUN mkdir -p /var/lib/parking && chown 65534:65534 /var/lib/parking
WORKDIR /var/lib/parking
USER 65534:65534
EXPOSE 8080
CMD ["parking_api"]
