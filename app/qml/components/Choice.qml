import QtQuick
import QtQuick.Controls
import ".."

// Labelled drop-down. `model` is a list of {key, label}; read `currentKey`.
Column {
    id: root
    property string label: ""
    property var model: []
    property string placeholder: "Choose"
    readonly property var currentKey: box.currentIndex >= 0 && box.currentIndex < model.length
        ? model[box.currentIndex].key : undefined
    readonly property var currentItem: box.currentIndex >= 0 && box.currentIndex < model.length
        ? model[box.currentIndex] : null

    // The key last chosen, by `select` or by hand. A rebuilt model makes the
    // box fall back to its first entry; `restore` puts this choice back.
    property var wanted: undefined

    function select(key) {
        wanted = key
        restore()
    }

    function restore() {
        for (var i = 0; i < model.length; i++) {
            if (model[i].key === wanted) { box.currentIndex = i; return }
        }
        box.currentIndex = -1
    }

    spacing: 6

    Text {
        text: root.label
        visible: root.label.length > 0
        color: Theme.muted
        font.family: Theme.uiFont
        font.pixelSize: 12
    }

    ComboBox {
        id: box
        width: root.width
        implicitHeight: Theme.controlHeight + 4
        model: root.model
        textRole: "label"
        currentIndex: -1
        onActivated: root.wanted = root.currentKey
        onModelChanged: root.restore()
        font.family: Theme.uiFont
        font.pixelSize: 14

        contentItem: Text {
            leftPadding: 12
            rightPadding: 28
            text: box.currentIndex >= 0 ? box.displayText : root.placeholder
            color: box.currentIndex >= 0 ? Theme.text : Theme.faint
            font: box.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        indicator: Text {
            x: box.width - width - 12
            anchors.verticalCenter: parent.verticalCenter
            text: ""
            font.family: Theme.iconFont
            font.pixelSize: 10
            color: Theme.muted
        }

        background: Rectangle {
            radius: Theme.controlRadius
            color: Theme.panel
            border.width: box.activeFocus || box.popup.visible ? 2 : 1
            border.color: box.activeFocus || box.popup.visible ? Theme.accent : Theme.line
        }

        delegate: ItemDelegate {
            id: option
            required property var modelData
            required property int index
            width: box.width - 2
            height: 34
            highlighted: box.highlightedIndex === index

            contentItem: Text {
                leftPadding: 4
                text: option.modelData.label
                color: Theme.text
                font: box.font
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            background: Rectangle {
                color: option.highlighted ? Theme.accentSoft : "transparent"
                radius: 4
            }
        }

        popup: Popup {
            y: box.height + 4
            width: box.width
            padding: 1
            implicitHeight: Math.min(contentItem.implicitHeight + 2, 264)

            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: box.popup.visible ? box.delegateModel : null
                currentIndex: box.highlightedIndex
                ScrollBar.vertical: ScrollBar {}
            }
            background: Rectangle {
                color: Theme.raised
                radius: Theme.controlRadius
                border.width: 1
                border.color: Theme.line
            }
        }
    }
}
