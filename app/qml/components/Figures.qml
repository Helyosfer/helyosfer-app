import QtQuick
import ".."

// A row of labelled results. `rows` is a list of {label, value, tone}, where
// tone 1 colors the value as a gain and -1 as a loss.
Row {
    id: root
    property var rows: []
    property int valueSize: 24

    Repeater {
        model: root.rows
        Column {
            required property var modelData
            width: root.width / Math.max(1, root.rows.length)
            spacing: 2
            Text {
                width: parent.width - 12
                text: modelData.label
                color: Theme.muted
                font.family: Theme.uiFont
                font.pixelSize: 12
                elide: Text.ElideRight
            }
            Text {
                text: modelData.value
                color: modelData.tone > 0 ? Theme.up : modelData.tone < 0 ? Theme.down : Theme.text
                font.family: Theme.displayFont
                font.pixelSize: root.valueSize
                font.weight: Font.Light
            }
        }
    }
}
