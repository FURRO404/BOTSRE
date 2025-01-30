{ pkgs }: {
  deps = [
    pkgs.geckodriver
    pkgs.python310                           # Python 3.10
    pkgs.chromium                            # Chromium browser
    pkgs.chromedriver                        # ChromeDriver for Chromium
    pkgs.python310Packages.selenium          # Selenium package for Python
    pkgs.python310Packages.pip               # Pip to install additional Python packages
  ];
}
