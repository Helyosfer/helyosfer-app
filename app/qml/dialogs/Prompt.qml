import QtQuick
import QtQuick.Controls
import ".."
import "../components"

// One-field dialog. `source` is the controller whose `message`, `busy` and
// `saved` drive it; the caller performs the write in `onSubmitted`.
Sheet {
    id: root
    property var source: null
    property var subject: null
    property string fieldLabel: ""
    property string fieldPlaceholder: ""
    property string confirmText: "Save"
    signal submitted(string text)

    function openFor(item, initialText) {
        subject = item
        field.text = initialText === undefined ? "" : initialText
        source.clearMessage()
        open()
        field.input.forceActiveFocus()
        field.input.selectAll()
    }

    Connections {
        target: root.source
        function onSaved() { if (root.visible) root.close() }
    }

    Field {
        id: field
        width: parent.width
        label: root.fieldLabel
        placeholder: root.fieldPlaceholder
        onAccepted: root.submitted(text)
    }

    Notice {
        width: parent.width
        text: root.source ? root.source.message : ""
    }

    footer: [
        PrimaryButton { quiet: true; text: "Cancel"; onClicked: root.close() },
        PrimaryButton {
            text: root.confirmText
            enabled: root.source ? !root.source.busy : false
            onClicked: root.submitted(field.text)
        }
    ]
}
