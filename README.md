    # SigmaOS-indicator-sound2

    Sound indicator alt

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/linuxmint/indicator-sound

    ## Design principles applied
    - **Least Astonishment**
- **Defensive Programming**
- **Fail-Fast**
- **KISS**
- **Separation of Concerns**
- **Deterministic Testing**

    ## Usage
    Verbs: `volume, output, mute, list-outputs`

    ```
    $ sigma-sound volume 70
volume = 70
$ sigma-sound mute
muted = true
$ sigma-sound output bluez_sink.XX
$ sigma-sound list-outputs

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
