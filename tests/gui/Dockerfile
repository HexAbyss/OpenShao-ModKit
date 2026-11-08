FROM debian:bookworm-slim
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-pip xvfb imagemagick x11-utils libgl1 libglx-mesa0 libgl1-mesa-dri libegl1 libxkbcommon0 libxrandr2 libxinerama1 libxcursor1 libxi6 xdotool x11-xserver-utils zenity > /dev/null 2>&1
RUN pip3 install -q --break-system-packages imgui-bundle numpy pillow unicorn 2>&1 | tail -1
