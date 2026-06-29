from models.structure_event import StructureEvent


class StructureConverter:

    def convert(self, swings):

        structure = []

        for swing in swings:

            structure.append(

                StructureEvent(

                    index=swing.index,
                    price=swing.price,
                    swing_type=swing.swing_type,
                    label=swing.label

                )

            )

        return structure