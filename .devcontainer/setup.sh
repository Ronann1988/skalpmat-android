#!/bin/bash
# Setup script for SKALPMAT Android development

set -e

echo "🚀 Setting up SKALPMAT Android build environment..."

# Update system
apt-get update

# Install essential build tools
apt-get install -y \
    git \
    ffmpeg \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-ttf-dev \
    libsdl2-gfx-dev \
    libfreetype6-dev \
    libjpeg-dev \
    libtiff-dev \
    tcl-dev \
    tk-dev \
    libsmpeg-dev \
    libgtk-3-dev \
    libgl1-mesa-dev \
    libglu1-mesa-dev \
    autoconf \
    automake \
    build-essential \
    cmake \
    libtool \
    pkg-config \
    zip \
    unzip \
    wget \
    curl

# Install OpenJDK 11
apt-get install -y openjdk-11-jdk

# Set JAVA_HOME
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
echo "export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64" >> ~/.bashrc

# Install Android SDK command-line tools
ANDROID_HOME=$HOME/android-sdk
mkdir -p $ANDROID_HOME
cd $ANDROID_HOME

wget -q https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O cmdtools.zip
unzip -q cmdtools.zip
mkdir -p cmdline-tools/latest
mv cmdline-tools/* cmdline-tools/latest/ 2>/dev/null || true
rm cmdtools.zip

export ANDROID_HOME=$HOME/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools
echo "export ANDROID_HOME=\$HOME/android-sdk" >> ~/.bashrc
echo "export PATH=\$PATH:\$ANDROID_HOME/cmdline-tools/latest/bin:\$ANDROID_HOME/platform-tools" >> ~/.bashrc

# Accept licenses
yes | sdkmanager --licenses

# Install required SDK packages
sdkmanager "platform-tools"
sdkmanager "platforms;android-31"
sdkmanager "build-tools;31.0.0"

# Install Buildozer dependencies
pip install buildozer cython==0.29.37

# Install Python dependencies
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy your synergy_bot_v6.py to synergy_bot_v7.py"
echo "2. Copy your .env file"
echo "3. Run: buildozer -v android debug"
echo ""
echo "Build will create APK in ./bin/ folder"