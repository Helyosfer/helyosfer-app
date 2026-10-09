import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Column {
    id: root
    spacing: Theme.gap

    Card {
        width: parent.width

        Column {
            width: parent.width
            spacing: 16

            Column {
                width: parent.width
                spacing: 3
                Text {
                    text: qsTr("Past balance")
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    text: qsTr("What your accounts held at the end of a past day, and what has moved the balance since.")
                    color: Theme.muted
                    font.family: Theme.uiFont
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
            }

            Flow {
                width: parent.width
                spacing: 12

                Field {
                    id: date
                    width: 200
                    label: qsTr("Date")
                    placeholder: qsTr("DD.MM.YYYY")
                    onAccepted: history.lookUp(text)
                }
                Item {
                    width: showButton.width
                    height: date.height
                    PrimaryButton {
                        id: showButton
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 2
                        text: history.busy ? qsTr("Looking…") : qsTr("Show")
                        enabled: !history.busy
                        onClicked: history.lookUp(date.text)
                    }
                }
            }

            Notice {
                width: parent.width
                text: history.message
            }
        }
    }

    Card {
        width: parent.width
        visible: history.hasResult

        Column {
            width: parent.width
            spacing: 12

            Row {
                width: parent.width

                Repeater {
                    model: [
                        { label: qsTr("In accounts on %1").arg(history.title), value: history.balanceText },
                        { label: qsTr("In savings goals"), value: history.savingsText }
                    ]
                    Column {
                        required property var modelData
                        width: parent.width / 2
                        spacing: 2
                        Text {
                            text: modelData.label
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                        Text {
                            text: modelData.value
                            color: Theme.text
                            font.family: Theme.displayFont
                            font.pixelSize: 26
                            font.weight: Font.Light
                        }
                    }
                }
            }

            Text {
                text: history.changeText
                color: Theme.direction(history.changeDirection)
                font.family: Theme.dataFont
                font.pixelSize: 12
            }

            Column {
                width: parent.width

                Text {
                    visible: history.sources.length === 0
                    text: qsTr("Nothing has moved the balance since that day.")
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }

                Repeater {
                    model: history.sources
                    Item {
                        id: line
                        required property var modelData
                        width: parent.width
                        height: 38

                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: line.modelData.label + "  ·  " + line.modelData.count
                            color: Theme.text
                            font.family: Theme.uiFont
                            font.pixelSize: 13
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: parent.right
                            text: line.modelData.amount
                            color: line.modelData.positive ? Theme.up : Theme.text
                            font.family: Theme.dataFont
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }
    }
}
