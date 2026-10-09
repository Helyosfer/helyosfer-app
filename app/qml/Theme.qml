pragma Singleton
import QtQuick

// One place for every color, size and font. Views read tokens, never literals.
QtObject {
    property bool dark: true

    readonly property color page: dark ? "#0d1117" : "#f3f5f8"
    readonly property color panel: dark ? "#131a24" : "#ffffff"
    readonly property color raised: dark ? "#19222f" : "#f7f8fa"
    readonly property color line: dark ? "#263142" : "#d9dee6"
    readonly property color lineSoft: dark ? "#1c2634" : "#e8ebf0"

    readonly property color text: dark ? "#e9edf3" : "#121a26"
    readonly property color muted: dark ? "#93a0b4" : "#56637a"
    readonly property color faint: dark ? "#64718a" : "#8490a5"

    readonly property color accent: dark ? "#9485f7" : "#5646d4"
    readonly property color accentSoft: dark ? "#2e9485f7" : "#1f5646d4"
    readonly property color onAccent: dark ? "#100c26" : "#ffffff"

    readonly property color up: dark ? "#6fcf9a" : "#1d7f4e"
    readonly property color down: dark ? "#ef8f86" : "#b8443a"
    readonly property color warn: dark ? "#ee8f5b" : "#ad4f1c"

    readonly property string uiFont: "Segoe UI"
    readonly property string displayFont: "Segoe UI"
    readonly property string dataFont: "Consolas"
    readonly property string iconFont: "Segoe MDL2 Assets"

    readonly property int radius: 8
    readonly property int controlRadius: 6
    readonly property int controlHeight: 36
    readonly property int gap: 20

    function direction(value) {
        return value > 0 ? up : value < 0 ? down : muted
    }
}
