import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Column {
    id: root
    signal editRequested(int transactionId)
    spacing: Theme.gap

    Component.onCompleted: calendar.refresh()

    MonthStepper {
        title: calendar.monthTitle
        onPrevious: calendar.previous()
        onNext: calendar.next()
    }

    Notice {
        width: parent.width
        text: calendar.message
    }

    Row {
        width: parent.width
        spacing: Theme.gap

        // -- Month grid -----------------------------------------------------
        Card {
            id: gridCard
            width: Math.min(parent.width * 0.55, 560)

            Column {
                width: parent.width
                spacing: 6

                Row {
                    Repeater {
                        model: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                        Text {
                            required property string modelData
                            width: grid.cell
                            horizontalAlignment: Text.AlignHCenter
                            text: modelData
                            color: Theme.muted
                            font.family: Theme.uiFont
                            font.pixelSize: 12
                        }
                    }
                }

                Grid {
                    id: grid
                    readonly property real cell: Math.floor(parent.width / 7)
                    columns: 7

                    Repeater {
                        model: calendar.cells

                        AbstractButton {
                            id: day
                            required property var modelData
                            readonly property bool chosen: modelData.day > 0
                                && modelData.day === calendar.selectedDay
                            width: grid.cell
                            height: 52
                            enabled: modelData.day > 0
                            hoverEnabled: true
                            Accessible.name: modelData.day > 0
                                ? modelData.day + ", " + modelData.count + " transactions" : ""
                            onClicked: calendar.selectDay(modelData.day)

                            background: Rectangle {
                                anchors.fill: parent
                                anchors.margins: 2
                                radius: Theme.controlRadius
                                color: day.chosen ? Theme.accentSoft
                                    : (day.hovered && day.enabled ? Theme.raised : "transparent")
                                border.width: day.modelData.today || day.visualFocus ? 1 : 0
                                border.color: day.visualFocus ? Theme.text : Theme.accent
                            }

                            contentItem: Item {
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    y: 8
                                    visible: day.modelData.day > 0
                                    text: day.modelData.day
                                    color: day.chosen ? Theme.text : Theme.muted
                                    font.family: Theme.uiFont
                                    font.pixelSize: 13
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    y: 28
                                    visible: day.modelData.count > 0
                                    text: day.modelData.count
                                    color: Theme.accent
                                    font.family: Theme.dataFont
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                }

                Text {
                    topPadding: 4
                    text: "The small number is how many transactions that day has."
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 11
                }
            }
        }

        // -- Selected day ---------------------------------------------------
        Card {
            width: parent.width - gridCard.width - Theme.gap

            Column {
                width: parent.width

                Text {
                    bottomPadding: 10
                    text: calendar.dayTitle
                    color: Theme.text
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Text {
                    visible: calendar.dayItems.length === 0
                    topPadding: 6
                    text: "No transactions on this day."
                    color: Theme.faint
                    font.family: Theme.uiFont
                    font.pixelSize: 13
                }

                Repeater {
                    model: calendar.dayItems

                    Item {
                        id: line
                        required property var modelData
                        width: parent.width
                        height: 44

                        Rectangle {
                            anchors.fill: parent
                            anchors.leftMargin: -8
                            anchors.rightMargin: -8
                            radius: 6
                            color: Theme.raised
                            visible: lineArea.containsMouse
                        }
                        Rectangle { width: parent.width; height: 1; color: Theme.lineSoft }
                        MouseArea {
                            id: lineArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.editRequested(line.modelData.id)
                        }
                        Text {
                            id: time
                            anchors.verticalCenter: parent.verticalCenter
                            width: 48
                            text: line.modelData.time
                            color: Theme.faint
                            font.family: Theme.dataFont
                            font.pixelSize: 12
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: time.right
                            anchors.right: sum.left
                            anchors.rightMargin: 12
                            spacing: 1
                            Text {
                                width: parent.width
                                text: line.modelData.title
                                color: Theme.text
                                font.family: Theme.uiFont
                                font.pixelSize: 13
                                elide: Text.ElideRight
                            }
                            Text {
                                width: parent.width
                                text: line.modelData.category
                                color: Theme.muted
                                font.family: Theme.uiFont
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                        }
                        Text {
                            id: sum
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.right: parent.right
                            text: line.modelData.amount
                            color: line.modelData.income ? Theme.up : Theme.text
                            font.family: Theme.dataFont
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }
    }
}
